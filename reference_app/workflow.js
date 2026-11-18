(() => {
  const $ = id => document.getElementById(id);
  const dialog = $('workflowDialog');
  const t = (ru, en) => localStorage.getItem('vrw-language') === 'en' ? en : ru;
  const documents = new Map();
  const writes = new Map();
  const optionSignatures = new WeakMap();
  const player = $('workflowPlayer');
  let activeTab;
  let selectedVideo;
  let locationMode = false;
  let inspectionFrames = [];
  let reviewDraft;

  function element(tag, content = '') {
    const node = document.createElement(tag);
    node.textContent = content;
    return node;
  }

  function button(label, action) {
    const node = element('button', label);
    node.type = 'button';
    node.className = 'secondary';
    node.onclick = action;
    return node;
  }

  function status(message = '', error = false) {
    const node = $('workflowStatus');
    node.hidden = !message;
    node.textContent = message;
    node.classList.toggle('workflow-error', error);
  }

  async function api(path, method = 'GET', data) {
    const response = await fetch(path, {
      method,
      ...(data === undefined ? {} : {
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(data),
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || t('Запрос не выполнен', 'Request failed'));
    return result;
  }

  async function busy(control, fn) {
    if (control.disabled) return;
    control.disabled = true;
    status();
    try {
      await fn();
    } catch (error) {
      status(error.message, true);
    } finally {
      control.disabled = false;
    }
  }

  function loadDocument(name) {
    if (!documents.has(name)) {
      documents.set(name, api('/api/workflow/' + name).catch(error => {
        documents.delete(name);
        throw error;
      }));
    }
    return documents.get(name);
  }

  async function documentRows(name) {
    return (await loadDocument(name)).items;
  }

  function writeRows(name, change) {
    const previous = writes.get(name) || Promise.resolve();
    const operation = previous.catch(() => {}).then(async () => {
      const {items,revision} = await loadDocument(name);
      const draft = structuredClone(items);
      change(draft);
      try {
        const updated = await api('/api/workflow/' + name, 'PUT', {items:draft,revision});
        documents.set(name, Promise.resolve(updated));
        return updated.items;
      } catch (error) {
        documents.delete(name);
        throw error;
      }
    });
    writes.set(name, operation);
    return operation;
  }

  function safePreview(url) {
    return typeof url === 'string' && (/^\/(archive|media)\//.test(url) || /^https?:\/\//i.test(url));
  }

  function localPreview(url) {
    return typeof url === 'string' && /^\/(archive|media)\//.test(url);
  }

  function imageReferences() {
    return window.workflowReferences().filter(ref =>
      ['Фото','Карусель'].includes(ref.type) && safePreview(ref.preview));
  }

  function photoValue(select) {
    return imageReferences().find(ref => ref.preview === select.value);
  }

  function fillOptions(select, references) {
    const signature = JSON.stringify(references.map(ref => [ref.preview,ref.title]));
    const lang = localStorage.getItem('vrw-language');
    const previous = optionSignatures.get(select);
    if (previous?.signature === signature && previous.lang === lang) return;
    optionSignatures.set(select,{signature,lang});
    const current = select.value;
    const placeholder = element('option', t('Выбрать', 'Choose'));
    placeholder.value = '';
    const options = references.map(ref => {
      const option = element('option', ref.title);
      option.value = ref.preview;
      option.dataset.referenceTitle = '';
      return option;
    });
    select.replaceChildren(placeholder, ...options);
    select.value = references.some(ref => ref.preview === current) ? current : '';
  }

  function updateOptions() {
    const photos = imageReferences();
    const local = photos.filter(ref => localPreview(ref.preview));
    for (const id of ['compareSource','compareTarget']) fillOptions($(id), photos);
    for (const id of ['reviewCandidate','visualExample']) fillOptions($(id), local);
    fillOptions($('workflowVideo'), window.workflowReferences().filter(ref =>
      ref.type === 'Видео' && localPreview(ref.preview)));
  }

  window.workflowArchiveUpdated = () => {
    if (dialog.open) updateOptions();
  };

  async function showTab(name, reference) {
    activeTab = name;
    status();
    if (name !== 'timeline') player.pause();
    for (const panel of dialog.querySelectorAll('[data-workflow-panel]')) {
      panel.hidden = panel.dataset.workflowPanel !== name;
    }
    for (const tab of dialog.querySelectorAll('[data-workflow-tab]')) {
      tab.setAttribute('aria-pressed', String(tab.dataset.workflowTab === name));
    }
    updateOptions();
    if (name === 'shots') await renderShots();
    if (name === 'timeline') {
      if (reference && localPreview(reference.preview)) {
        $('workflowVideo').value = reference.preview;
        await selectVideo();
      } else {
        if (!$('workflowVideo').value && $('workflowVideo').options.length > 1) {
          $('workflowVideo').selectedIndex = 1;
        }
        await selectVideo();
      }
    }
    if (name === 'comparisons') {
      const photos = window.workflowSelection().filter(ref => safePreview(ref.preview) && ref.type === 'Фото');
      if (photos.length >= 2 && !$('compareSource').value && !$('compareTarget').value) {
        $('compareSource').value = photos[0].preview;
        $('compareTarget').value = photos[1].preview;
      }
      updateComparison();
      await renderComparisons();
    }
    if (name === 'search' && reference) {
      $('visualExample').value = localPreview(reference.preview) ? reference.preview : '';
      if ($('visualExample').value) $('visualSearchForm').requestSubmit();
      else status(t('Для поиска по примеру нужно локальное фото', 'Example search needs a local photo'), true);
    }
    if (name === 'reviews') {
      if (!inspectionFrames.length) addReviewFrames(window.workflowSelection());
      renderReviewFrames();
      await renderSavedReviews();
    }
  }

  window.openWorkflow = (name = 'shots', reference) => {
    if (!dialog.open) dialog.showModal();
    showTab(name, reference).catch(error => status(error.message, true));
  };
  $('workflowClose').onclick = () => dialog.close();
  dialog.addEventListener('close', () => {
    player.pause();
    $('reviewKey').value = '';
  });
  $('openWorkflow').onclick = () => window.openWorkflow();
  $('boardWorkflow').onclick = () => window.openWorkflow('shots');
  $('openGemini').onclick = () => window.openWorkflow('reviews');
  for (const tab of dialog.querySelectorAll('[data-workflow-tab]')) {
    tab.onclick = () => window.openWorkflow(tab.dataset.workflowTab);
  }

  function download(blob, filename) {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 30000);
  }

  function downloadText(contents, filename) {
    download(new Blob([contents], {type:'text/plain;charset=utf-8'}), filename);
  }

  function toBlob(canvas, type = 'image/png') {
    return new Promise((resolve, reject) => canvas.toBlob(
      blob => blob ? resolve(blob) : reject(new Error(t('Не удалось создать изображение', 'Could not create image'))),
      type,
    ));
  }

  function addShot(ref) {
    return {id:crypto.randomUUID(), title:ref?.title || '', preview:ref?.preview || '',
            url:ref?.url || '', note:'', done:false};
  }

  function updateShot(id, properties) {
    return writeRows('shots', rows => {
      const row = rows.find(shot => shot.id === id);
      if (row) Object.assign(row, properties);
    });
  }

  async function renderShots() {
    const shots = await documentRows('shots');
    const list = $('shotList');
    list.replaceChildren();
    if (!shots.length) {
      list.append(element('li',t('Добавьте кадры с доски или из выделения.', 'Add shots from the board or selection.')));
      return;
    }
    shots.forEach((shot, index) => {
      const row = element('li');
      row.className = 'workflow-row shot-row';
      const doneLabel = element('label');
      const done = element('input');
      done.type = 'checkbox';
      done.checked = Boolean(shot.done);
      doneLabel.append(done, t('Снято', 'Shot'));
      done.onchange = async () => {
        try { await updateShot(shot.id,{done:done.checked}); }
        catch (error) { done.checked = !done.checked; status(error.message, true); }
      };
      row.append(element('span', String(index+1)), doneLabel);
      if (safePreview(shot.preview) && !/\.(mp4|mov|webm|ogv)(?:[?#]|$)/i.test(shot.preview)) {
        const image = element('img');
        image.className = 'workflow-thumb';
        image.alt = '';
        image.loading = 'lazy';
        image.src = shot.preview;
        row.append(image);
      }
      const fields = element('div');
      fields.className = 'shot-fields';
      if (locationMode) fields.append(element('strong',shot.title || t('Без названия','Untitled')),element('p',shot.note));
      else {
        const title = element('input');
        title.value = shot.title;
        title.maxLength = 180;
        title.placeholder = t('Название кадра', 'Shot title');
        title.setAttribute('aria-label', title.placeholder);
        const notes = element('textarea');
        notes.value = shot.note;
        notes.rows = 2;
        notes.maxLength = 1000;
        notes.placeholder = t('Свет, крупность, поза, движение', 'Lighting, framing, pose, motion');
        notes.setAttribute('aria-label', notes.placeholder);
        title.onchange = () => updateShot(shot.id,{title:title.value}).catch(error => status(error.message,true));
        notes.onchange = () => updateShot(shot.id,{note:notes.value}).catch(error => status(error.message,true));
        fields.append(title, notes);
      }
      row.append(fields);
      if (!locationMode) {
        const sort = delta => writeRows('shots', rows => {
          const from = rows.findIndex(item => item.id === shot.id);
          const to = from+delta;
          if (from >= 0 && to>=0 && to<rows.length) [rows[from], rows[to]] = [rows[to], rows[from]];
        }).then(renderShots);
        const controls = element('div');
        controls.className = 'workflow-controls';
        const up = button('↑', event => busy(event.currentTarget, () => sort(-1)));
        const down = button('↓', event => busy(event.currentTarget, () => sort(1)));
        up.setAttribute('aria-label', t('Переместить вверх','Move up'));
        down.setAttribute('aria-label', t('Переместить вниз','Move down'));
        up.disabled = index===0;
        down.disabled = index===shots.length-1;
        controls.append(up, down, button(t('Убрать','Remove'), event => busy(event.currentTarget, async () => {
          await writeRows('shots', rows => {
            const found = rows.findIndex(item => item.id === shot.id);
            if (found !== -1) rows.splice(found,1);
          });
          await renderShots();
        })));
        row.append(controls);
      }
      list.append(row);
    });
  }

  function addShots(references) {
    if (!references.length) throw new Error(t('Сначала добавьте материалы на доску или выделите их в архиве.', 'Add items to the board or select them in the archive first.'));
    return writeRows('shots', rows => {
      const local = new Set(rows.map(row => row.preview).filter(Boolean));
      for (const ref of references) {
        if (ref?.preview && local.has(ref.preview)) continue;
        rows.push(addShot(ref));
        if (ref?.preview) local.add(ref.preview);
      }
    }).then(renderShots);
  }
  $('shotFromBoard').onclick = event => busy(event.currentTarget, async () => addShots(await window.workflowBoardItems()));
  $('shotFromArchive').onclick = event => busy(event.currentTarget, () => addShots(window.workflowSelection()));
  $('shotBlank').onclick = event => busy(event.currentTarget, () => addShots([null]));
  $('shotMode').onclick = event => {
    locationMode = !locationMode;
    event.currentTarget.setAttribute('aria-pressed', String(locationMode));
    renderShots().catch(error => status(error.message,true));
  };
  $('shotExport').onclick = event => busy(event.currentTarget, async () => {
    await writes.get('shots');
    const shots = await documentRows('shots');
    if (!shots.length) throw new Error(t('Список пуст', 'The list is empty'));
    downloadText(shots.map((shot,index) =>
      `${index+1}. [${shot.done?'x':' '}] ${shot.title}\n${shot.note}${/^https?:\/\//i.test(shot.url)?'\n'+shot.url:''}`).join('\n\n'), 'shot-list.txt');
  });

  function stamp(time) {
    const ms = Math.round(time*1000);
    return `${String(Math.floor(ms/60000)).padStart(2,'0')}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}.${String(ms%1000).padStart(3,'0')}`;
  }

  async function upload(file, name = file.name) {
    if (!file.size || file.size > 512*1024*1024) throw new Error(t('Файл должен быть меньше 512 МБ и не пустым','File must be nonempty and below 512 MB'));
    const response = await fetch('/api/uploads?name='+encodeURIComponent(name), {
      method:'POST', headers:{'Content-Type':'application/octet-stream'}, body:file,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || t('Загрузка не удалась','Upload failed'));
    return result.url;
  }

  async function saveReference({title, preview, type, url = '', description = '', sourceTime}) {
    const ref = {title,preview,type,url,description,added:new Date().toISOString().slice(0,10)};
    const {id} = await api('/api/references','POST',ref);
    await window.refreshReferences();
    updateOptions();
    return {...ref,id,sourceTime};
  }

  async function selectVideo() {
    const next = window.workflowReferences().find(ref => ref.preview === $('workflowVideo').value);
    if (selectedVideo?.preview !== next?.preview) {
      selectedVideo = next;
      player.pause();
      if (next) player.src = next.preview;
      else player.removeAttribute('src');
      player.load();
      $('workflowTime').textContent = stamp(0);
      $('clipStart').value = $('clipEnd').value = 0;
    }
    await renderMarkers();
  }
  $('workflowVideo').onchange = () => selectVideo().catch(error => status(error.message,true));
  player.addEventListener('timeupdate', () => { $('workflowTime').textContent = stamp(player.currentTime); });
  player.addEventListener('error', () => {
    if (activeTab === 'timeline' && selectedVideo) status(t('Видео недоступно или формат не поддерживается браузером.','Video is unavailable or unsupported by this browser.'),true);
  });
  $('useClipStart').onclick = () => { $('clipStart').value = player.currentTime.toFixed(3); };
  $('useClipEnd').onclick = () => { $('clipEnd').value = player.currentTime.toFixed(3); };
  $('workflowVideoUpload').onchange = async event => {
    const input = event.currentTarget;
    const file = input.files[0];
    if (!file) return;
    await busy(input, async () => {
      const preview = await upload(file);
      await saveReference({title:file.name,preview,type:'Видео'});
      $('workflowVideo').value = preview;
      await selectVideo();
    });
    input.value = '';
  };

  function readyVideo() {
    if (!selectedVideo || player.readyState < 2 || player.seeking) throw new Error(t('Дождитесь загрузки видео','Wait for the video to load'));
    return selectedVideo;
  }

  async function renderMarkers() {
    const markers = await documentRows('timeline');
    const list = $('timelineMarkers');
    list.replaceChildren();
    if (!selectedVideo) return;
    markers.filter(row => row.preview === selectedVideo.preview).sort((a,b)=>a.time-b.time).forEach(marker => {
      const row = element('li');
      row.className = 'workflow-row';
      row.append(button(stamp(marker.time), () => { player.currentTime = marker.time; }), element('span', marker.note));
      row.append(button(t('Убрать','Remove'), event => busy(event.currentTarget, async () => {
        await writeRows('timeline', rows => {
          const index = rows.findIndex(item => item.id === marker.id);
          if (index !== -1) rows.splice(index,1);
        });
        await renderMarkers();
      })));
      list.append(row);
    });
  }

  $('addMarker').onclick = event => busy(event.currentTarget, async () => {
    const video = readyVideo();
    const time = player.currentTime;
    const field = $('markerLabel');
    const note = field.value.trim() || t('Склейка','Cut');
    await writeRows('timeline', rows => rows.push({id:crypto.randomUUID(),preview:video.preview,time,note}));
    field.value = '';
    await renderMarkers();
  });

  $('exportTimeline').onclick = event => busy(event.currentTarget, async () => {
    if (!selectedVideo) throw new Error(t('Выберите видео','Choose a video'));
    const markers=(await documentRows('timeline')).filter(marker=>marker.preview===selectedVideo.preview);
    if (!markers.length) throw new Error(t('Поставьте хотя бы одну метку','Place at least one marker'));
    markers.sort((a,b)=>a.time-b.time);
    downloadText([selectedVideo.title,...markers.map(marker=>`${stamp(marker.time)}  ${marker.note}`)].join('\n'),
                 'video-breakdown.txt');
  });

  async function captureFrame(toBoard) {
    const video = readyVideo();
    const time = player.currentTime;
    const frame = document.createElement('canvas');
    const scale = Math.min(1,1920/Math.max(player.videoWidth,player.videoHeight));
    frame.width = Math.max(1,Math.round(player.videoWidth*scale));
    frame.height = Math.max(1,Math.round(player.videoHeight*scale));
    frame.getContext('2d').drawImage(player,0,0,frame.width,frame.height);
    const preview = await upload(await toBlob(frame),'frame.png');
    const detail = `${video.title} · ${stamp(time)}`;
    const ref = await saveReference({title:detail,preview,type:'Фото',url:video.url,sourceTime:time,
      description:[detail,$('markerLabel').value.trim()].filter(Boolean).join('\n')});
    if (toBoard) {
      await window.addReferencesToBoard([ref]);
      dialog.close();
      window.showBoard();
    } else status(t('Стоп-кадр сохранён в архив','Frame saved to the archive'));
  }

  $('captureFrame').onclick = event => busy(event.currentTarget, () => captureFrame(false));
  $('captureToBoard').onclick = event => busy(event.currentTarget, () => captureFrame(true));
  $('saveClip').onclick = event => busy(event.currentTarget, async () => {
    const video = readyVideo();
    const start = Number($('clipStart').value);
    const end = Number($('clipEnd').value);
    if (!Number.isFinite(player.duration) || !(start>=0 && end>start && end<=player.duration+0.001)) {
      throw new Error(t('Выберите начало и конец внутри видео','Choose start and end inside the video'));
    }
    status(t('Готовим фрагмент…','Preparing the clip…'));
    const {url:preview} = await api('/api/workflow/clip','POST',{preview:video.preview,start,end});
    const title = `${video.title} · ${stamp(start)}–${stamp(end)}`;
    await saveReference({title,preview,type:'Видео',url:video.url,description:title,sourceTime:start});
    status(t('Фрагмент сохранён в архив','Clip saved to the archive'));
  });

  function comparisonSettings() {
    return {zoom:Number($('compareZoom').value), x:Number($('compareX').value), y:Number($('compareY').value),
            wipe:Number($('compareWipe').value), overlay:$('compareMode').getAttribute('aria-pressed') === 'true'};
  }

  function updateComparison() {
    const settings = comparisonSettings();
    $('comparisonStage').classList.toggle('comparison-overlay',settings.overlay);
    $('comparisonStage').style.setProperty('--wipe',settings.wipe+'%');
    $('compareWipeControl').hidden = !settings.overlay;
    const sides = [
      [$('compareLeftImage'),$('compareSource'),settings.x,settings.y],
      [$('compareRightImage'),$('compareTarget'),0,0],
    ];
    for (const [image,select,x,y] of sides) {
      if (safePreview(select.value)) {
        if (image.getAttribute('src') !== select.value) image.src = select.value;
        image.hidden = false;
      } else {
        image.removeAttribute('src');
        image.hidden = true;
      }
      image.style.transform = `translate(${x}%, ${y}%) scale(${settings.zoom})`;
    }
  }

  for (const id of ['compareSource','compareTarget','compareZoom','compareX','compareY','compareWipe']) {
    $(id).addEventListener('input',updateComparison);
  }
  $('compareMode').onclick = event => {
    const control = event.currentTarget;
    control.setAttribute('aria-pressed',String(control.getAttribute('aria-pressed') !== 'true'));
    updateComparison();
  };
  $('compareUpload').onchange = async event => {
    const input = event.currentTarget;
    const file = input.files[0];
    if (!file) return;
    await busy(input, async () => {
      const preview = await upload(file);
      await saveReference({title:file.name,preview,type:'Фото'});
      $('compareSource').value = preview;
      updateComparison();
    });
    input.value = '';
  };

  function selectedComparison() {
    const source = photoValue($('compareSource'));
    const target = photoValue($('compareTarget'));
    if (!source || !target) throw new Error(t('Выберите исходник и референс','Choose a source and a reference'));
    return {source:source.preview,target:target.preview,title:`${source.title} / ${target.title}`,
            notes:$('compareNotes').value,settings:comparisonSettings()};
  }

  async function renderComparisons() {
    const choices = $('savedComparisons');
    const rows = await documentRows('comparisons');
    choices.replaceChildren(element('option', t('Выбрать','Choose')));
    choices.firstElementChild.value = '';
    for (const item of rows) {
      const option = element('option',item.title);
      option.value = item.id;
      choices.append(option);
    }
  }
  $('compareSave').onclick = event => busy(event.currentTarget, async () => {
    const comparison = selectedComparison();
    const rows = await writeRows('comparisons', saved => {
      const existing = saved.find(item => item.id === $('savedComparisons').value);
      if (existing && existing.source === comparison.source && existing.target === comparison.target) {
        Object.assign(existing,comparison);
        comparison.id = existing.id;
      } else {
        comparison.id = crypto.randomUUID();
        saved.unshift(comparison);
      }
    });
    await renderComparisons();
    $('savedComparisons').value = rows.find(item => item.id === comparison.id).id;
    status(t('Сравнение сохранено','Comparison saved'));
  });
  $('savedComparisons').onchange = async event => {
    try {
      const selected = (await documentRows('comparisons')).find(item => item.id === event.target.value);
      if (!selected) return;
      $('compareSource').value = selected.source;
      $('compareTarget').value = selected.target;
      $('compareNotes').value = selected.notes;
      for (const [key,id] of [['zoom','compareZoom'],['x','compareX'],['y','compareY'],['wipe','compareWipe']]) {
        $(id).value = selected.settings[key];
      }
      $('compareMode').setAttribute('aria-pressed',String(selected.settings.overlay));
      updateComparison();
    } catch (error) { status(error.message,true); }
  };

  $('compareExportNotes').onclick = event => busy(event.currentTarget, async () => {
    const {title,notes} = selectedComparison();
    const records = [photoValue($('compareSource')),photoValue($('compareTarget'))];
    const sources = records.map(ref=> /^https?:\/\//i.test(ref.url) ? `${ref.title}: ${ref.url}` : ref.title);
    downloadText([title,notes,...sources].join('\n\n'),'comparison-notes.txt');
  });

  function exportImage(src) {
    return new Promise((resolve,reject)=>{
      const image = new Image();
      const timeout = setTimeout(()=>reject(new Error(t('Изображение не загрузилось','Image did not load'))),12000);
      image.crossOrigin = 'anonymous';
      image.onload = () => { clearTimeout(timeout); resolve(image); };
      image.onerror = () => {
        clearTimeout(timeout);
        reject(new Error(t('Скачайте внешнее фото и загрузите его как локальный файл.', 'Download the external photo and import it as a local file.')));
      };
      image.src = src;
    });
  }

  function drawComparison(context,image,origin,width,height,settings,offsetX,offsetY,visibleWidth=width) {
    const scale = Math.min(width/image.naturalWidth,height/image.naturalHeight)*settings.zoom;
    const drawWidth = image.naturalWidth*scale;
    const drawHeight = image.naturalHeight*scale;
    context.save();
    context.beginPath();
    context.rect(origin,0,visibleWidth,height);
    context.clip();
    context.fillStyle='#111';
    context.fillRect(origin,0,width,height);
    context.drawImage(image,origin+(width-drawWidth)/2+width*offsetX/100,
                      (height-drawHeight)/2+height*offsetY/100,drawWidth,drawHeight);
    context.restore();
  }

  $('compareExport').onclick = event => busy(event.currentTarget, async () => {
    const comparison=selectedComparison();
    const [source,target]=await Promise.all([exportImage(comparison.source),exportImage(comparison.target)]);
    const {settings}=comparison;
    const output=document.createElement('canvas');
    const width=960;
    const height=720;
    output.width=settings.overlay?width:2*width;
    output.height=height;
    const context=output.getContext('2d');
    drawComparison(context,source,0,width,height,settings,settings.x,settings.y);
    drawComparison(context,target,settings.overlay?0:width,width,height,settings,0,0,
                   settings.overlay?width*settings.wipe/100:width);
    download(await toBlob(output),'comparison.png');
  });

  function renderVisualResults(result) {
    const results = $('visualResults');
    results.replaceChildren();
    const explanations = [];
    if (result.byExample) explanations.push(t('Сходство с выбранным кадром','Similarity to the chosen frame'));
    if (result.signals.length) explanations.push(t('Признаки','Signals')+': '+result.signals.join(', '));
    if (result.metadata) explanations.push(t('Совпадения в описаниях и тегах','Matches in descriptions and tags'));
    $('visualSignals').textContent = result.items.length ? explanations.join(' · ') : t('Ничего не найдено','No matches');
    for (const ref of result.items) {
      const card = element('article');
      const image = element('img');
      image.alt = '';
      image.loading = 'lazy';
      if (safePreview(ref.preview)) image.src = ref.preview;
      const toolbar = element('div');
      toolbar.className='workflow-controls';
      toolbar.append(button(t('Открыть','Open'), () => {
        dialog.close();
        window.openReferenceCard(ref);
      }),button(t('На доску','Add to board'), event=>busy(event.currentTarget,async()=>{
        await window.addReferencesToBoard([ref]);
        dialog.close();
        window.showBoard();
      })));
      card.append(image,element('strong',ref.title),toolbar);
      results.append(card);
    }
  }
  $('visualSearchForm').onsubmit = event => {
    event.preventDefault();
    return busy($('runVisualSearch'),async()=>{
      const query=$('visualQuery').value.trim();
      const example=$('visualExample').value;
      if (!query && !example) throw new Error(t('Введите запрос или выберите фото','Enter a query or choose a photo'));
      $('visualResults').replaceChildren();
      $('visualSignals').textContent='';
      status(t('Проверяем архив. Первый поиск может занять немного времени…','Checking the archive. The first search may take a moment…'));
      const result=await api('/api/workflow/search','POST',{query,example,lightOnly:$('visualByLight').checked});
      renderVisualResults(result);
      status();
    });
  };

  function addReviewFrames(references) {
    for (const ref of references) {
      if (inspectionFrames.length>=8) break;
      if (!localPreview(ref.preview) || !['Фото','Карусель'].includes(ref.type)) continue;
      if (inspectionFrames.some(item=>item.preview===ref.preview)) continue;
      inspectionFrames.push(ref);
    }
  }

  function referenceLink(ref, index) {
    const link=element('a', `${t('Кадр','Frame')} ${index} · ${ref.title}`);
    if (localPreview(ref.preview)) link.href=ref.preview;
    link.target='_blank';
    link.rel='noopener';
    return link;
  }

  function renderReviewFrames() {
    const list=$('reviewFrames');
    list.replaceChildren();
    inspectionFrames.forEach((ref,index)=>{
      const row=element('li');
      row.className='workflow-row';
      row.append(referenceLink(ref,index+1),button(t('Убрать','Remove'),()=>{
        inspectionFrames.splice(index,1);
        renderReviewFrames();
      }));
      list.append(row);
    });
  }
  $('addReviewFrame').onclick=()=>{
    const choice=photoValue($('reviewCandidate'));
    if (choice) addReviewFrames([choice]);
    renderReviewFrames();
  };
  $('reviewFromSelection').onclick=()=>{
    addReviewFrames(window.workflowSelection());
    renderReviewFrames();
    if (!inspectionFrames.length) status(t('Выделите локальные фото или добавьте кадры видео.','Select local photos or add video frames.'),true);
  };

  function reviewObservations(root,observations,frames) {
    for (const observation of observations) {
      const row=element('div');
      row.append(element('p',observation.text));
      const evidence=element('div');
      evidence.className='workflow-controls';
      for (const index of observation.frames) {
        const ref=frames[index-1];
        if (ref) evidence.append(referenceLink(ref,index));
      }
      row.append(evidence);
      root.append(row);
    }
  }

  $('runReview').onclick=event=>busy(event.currentTarget,async()=>{
    if (!inspectionFrames.length) throw new Error(t('Добавьте хотя бы один локальный кадр','Add at least one local frame'));
    const snapshots=inspectionFrames.map(({title,preview})=>({title,preview}));
    $('workReviewResult').hidden=true;
    status(t('Gemini разбирает выбранные кадры…','Gemini is reviewing the selected frames…'));
    const brief=$('reviewBrief').value;
    const result=await api('/api/workflow/review','POST',{
      key:$('reviewKey').value,model:$('reviewModel').value,brief,
      language:localStorage.getItem('vrw-language')||'ru',refs:snapshots,
    });
    reviewDraft={id:crypto.randomUUID(),created:new Date().toISOString(),model:result.model,
                 frames:snapshots,observations:result.observations,brief};
    $('reviewNote').value=result.summary;
    const evidence=$('reviewEvidence');
    evidence.replaceChildren();
    reviewObservations(evidence,result.observations,snapshots);
    $('workReviewResult').hidden=false;
    status();
  });

  async function renderSavedReviews() {
    const root=$('savedReviews');
    const reviews=await documentRows('reviews');
    root.replaceChildren();
    for (const review of reviews) {
      const detail=element('details');
      const date=new Date(review.created).toLocaleDateString();
      detail.append(element('summary',`${date} · ${review.brief||review.model}`),element('p',review.note));
      reviewObservations(detail,review.observations,review.frames);
      detail.append(button(t('Править заметку','Edit note'),()=>{
        reviewDraft=review;
        $('reviewNote').value=review.note;
        const evidence=$('reviewEvidence');
        evidence.replaceChildren();
        reviewObservations(evidence,review.observations,review.frames);
        $('workReviewResult').hidden=false;
        $('reviewNote').focus();
      }));
      root.append(detail);
    }
  }
  $('saveReview').onclick=event=>busy(event.currentTarget,async()=>{
    if (!reviewDraft) return;
    const note=$('reviewNote').value.trim();
    if (!note) throw new Error(t('Напишите заметку','Write a note'));
    await writeRows('reviews', rows=>{
      const existing=rows.find(item=>item.id===reviewDraft.id);
      if (existing) existing.note=note;
      else rows.unshift({...reviewDraft,note});
    });
    await renderSavedReviews();
    status(t('Заметка сохранена к доске','Note saved to the board'));
  });
})();
