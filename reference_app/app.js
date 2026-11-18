const $=s=>document.querySelector(s), grid=$('#grid'), dialog=$('#dialog'), form=$('#form'); let refs=[], archive=[], current=null, view="archive", initialized=false;
let mediaFilter="", reverseOrder=false;
const selectedReferences=new Set();
const selectionButton=$('#toggleSelection'), boardButton=$('#sendToBoard'), selectionStatus=$('#selectionStatus');
let selectionMode=false, sendingSelection=false, selectionAnchor=null;
const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tags=s=>String(s||'').split(',').map(x=>x.trim()).filter(Boolean);
function media(r){let p=r.preview||''; if(r.type==='Аудио')return '<div class="audio-card"><span aria-hidden="true">♪</span><small>MP3</small></div>';  if(!/^(https?:\/\/|\/archive\/|\/media\/)/i.test(p)) return '<div class="placeholder"><span>↗</span><small>БЕЗ ПРЕВЬЮ</small></div>'; let src=esc(p); return r.type==='Видео'&&/\.(mp4|webm|mov|ogv|ogg)([?#]|$)/i.test(p)?`<video src="${src}" muted playsinline preload="metadata"></video>`:`<img src="${src}" loading="lazy" alt="" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><div class="placeholder" hidden><span>↗</span><small>ПРЕВЬЮ НЕДОСТУПНО</small></div>`}
async function load(){let res=await fetch('/api/references'); if(!res.ok) throw Error('Не удалось загрузить коллекцию'); refs=await res.json(); let a=await fetch('/api/archive'); if(a.ok) archive=await a.json(); if(!initialized){initialized=true;switchView('archive')}else render()}
function archiveItems(){
  const items=[...refs,...archive];
  if(view==='archive') return items;
  if(!window.folderSelection) return refs;
  const collectionKeys=new Set(window.folderSelection.items);
  return items.filter(item=>collectionKeys.has(window.referenceKey(item)));
}

function mediaType(item){
  if(/\.gif(?:[?#]|$)/i.test(item.preview||'')) return 'gif';
  if(item.type==='Фото') return 'photo';
  if(item.type==='Видео') return 'video';
  return 'other';
}

function render(){
  const list=archiveItems();
  const query=$('#search').value.toLocaleLowerCase().trim();
  const tagFilter=$('#tagFilter');
  const tag=tagFilter.value;
  const allTags=[...new Set(list.flatMap(item=>tags(item.tags)))].sort((a,b)=>a.localeCompare(b,'ru'));
  tagFilter.innerHTML='<option value="">Все теги</option>'+allTags.map(t=>`<option ${t===tag?'selected':''}>${esc(t)}</option>`).join('');
  const found=list.filter(item=>
    (!query||[item.title,item.author,item.description,item.tags].some(value=>String(value||'').toLocaleLowerCase().includes(query))) &&
    (!mediaFilter||mediaType(item)===mediaFilter) &&
    (!tagFilter.value||tags(item.tags).includes(tagFilter.value))
  );
  if(reverseOrder) found.reverse();
  $('#count').textContent=found.length+' / '+list.length;
  $('#empty').hidden=list.length>0;
  $('#noResults').hidden=list.length===0||found.length>0;
  grid.innerHTML=found.map(item=>{
    const type=mediaType(item);
    const badge=type==='gif'?'GIF':type==='video'?'Видео':'';
    return `<button type="button" class="card" data-id="${esc(item.id)}" aria-label="${esc(item.title)}" title="${esc(item.title)}"><div class="media">${media(item)}${badge?`<span class="media-badge">${badge}</span>`:''}</div><div class="card-info"><div class="card-top"><h3>${esc(item.title)}</h3></div><p>${esc(item.author||'Автор не указан')}</p><div class="chips">${tags(item.tags).slice(0,3).map(tag=>`<span>${esc(tag)}</span>`).join('')}</div></div></button>`;
  }).join('');
  updateReferenceSelection();
}

function updateSourceHint(){try{let host=new URL(form.elements.url.value).hostname.toLowerCase();$('#sourceHint').hidden=!(host==='pin.it'||host==='pinterest.com'||host.endsWith('.pinterest.com'))}catch(e){$('#sourceHint').hidden=true}}
form.elements.url.addEventListener('input',updateSourceHint);
function updateAudioPlayer(){let player=$('#audioPlayer'),p=form.elements.preview.value.trim();let valid=form.elements.type.value==='Аудио' && /^(https?:\/\/|\/media\/)/i.test(p) && /\.mp3([?#]|$)/i.test(p);player.pause();$('#audioPlayerWrap').hidden=!valid;if(valid){player.src=p;player.load()}else{player.removeAttribute('src');player.load()}}
function updateVideoPlayer(){let player=$('#videoPlayer'),p=form.elements.preview.value.trim();let valid=form.elements.type.value==='Видео' && /^(https?:\/\/|\/media\/|\/archive\/)/i.test(p) && /\.(mp4|webm|mov|ogv|ogg)([?#]|$)/i.test(p);player.pause();$('#videoPlayerWrap').hidden=!valid;if(valid){player.src=p;player.load()}else{player.removeAttribute('src');player.load()}}
function updatePlayers(){updateVideoPlayer();updateAudioPlayer()}
form.elements.type.addEventListener('change',updatePlayers);form.elements.preview.addEventListener('change',updatePlayers);$('#videoUpload').addEventListener('change',e=>{if(e.target.files.length){$('#audioUpload').value='';form.elements.type.value='Видео'}});$('#audioUpload').addEventListener('change',e=>{if(e.target.files.length){$('#videoUpload').value='';form.elements.type.value='Аудио'}});dialog.addEventListener('close',()=>{for(const p of [$('#videoPlayer'),$('#audioPlayer')]){p.pause();p.removeAttribute('src');p.load()}});
function open(r){if(window.onReferenceOpen)window.onReferenceOpen(r);current=r?.archived?null:(r?.id||null); form.reset(); for(let el of form.elements) if(el.name&&r) el.value=r[el.name]||''; if(!r || r.archived){let d=new Date(); d.setMinutes(d.getMinutes()-d.getTimezoneOffset()); form.elements.added.value=d.toISOString().slice(0,10)} $('#formTitle').textContent=r?.archived?'Архивный материал':r?'Карточка референса':'Новый референс'; $('#notice').textContent=r?.archived?'Просмотр локального архива. Сохранение создаст отдельную редактируемую карточку; исходный файл и индекс останутся без изменений. Дата — дата создания карточки.':'Автоматический импорт из Instagram не подключён. Вставьте ссылку и заполните карточку вручную.'; $('#delete').hidden=!r || !!r.archived; $('#error').textContent=''; updateSourceHint(); updatePlayers(); dialog.showModal()}
function updateReferenceSelection(){
  const selecting=view==='archive' && selectionMode;
  selectionButton.hidden=view!=='archive';
  selectionButton.disabled=sendingSelection;
  selectionButton.setAttribute('aria-pressed',String(selecting));
  selectionButton.textContent=selecting?'Готово':'Выбрать';
  boardButton.hidden=!selecting;
  boardButton.disabled=selectedReferences.size===0 || sendingSelection;
  const addLabel=localStorage.getItem('vrw-language')==='en'?'Add to board':'На доску';
  boardButton.textContent=selectedReferences.size?`${addLabel} (${selectedReferences.size})`:addLabel;
  grid.classList.toggle('selecting',selecting);
  for(const card of grid.querySelectorAll('.card')){
    if(selecting) card.setAttribute('aria-pressed',String(selectedReferences.has(card.dataset.id)));
    else card.removeAttribute('aria-pressed');
  }
}

function clearSelection(){
  selectionMode=false;
  selectionAnchor=null;
  selectedReferences.clear();
  selectionStatus.hidden=true;
}

selectionButton.onclick=()=>{
  if(selectionMode) clearSelection();
  else selectionMode=true;
  updateReferenceSelection();
};

grid.onclick=event=>{
  const card=event.target.closest('.card');
  if(!card) return;
  const ref=archiveItems().find(item=>item.id===card.dataset.id);
  if(!ref) return;
  if(view!=='archive'||(!selectionMode&&!event.metaKey&&!event.ctrlKey&&!event.shiftKey)){
    open(ref);
    return;
  }
  if(sendingSelection) return;
  selectionMode=true;
  selectionStatus.hidden=true;
  const visibleIds=[...grid.querySelectorAll('.card')].map(node=>node.dataset.id);
  const from=visibleIds.indexOf(selectionAnchor), to=visibleIds.indexOf(ref.id);
  if(event.shiftKey&&from!==-1){
    for(const id of visibleIds.slice(Math.min(from,to),Math.max(from,to)+1)) selectedReferences.add(id);
  }else if(selectedReferences.has(ref.id)) selectedReferences.delete(ref.id);
  else selectedReferences.add(ref.id);
  selectionAnchor=ref.id;
  updateReferenceSelection();
};

boardButton.onclick=async()=>{
  if(sendingSelection || !selectedReferences.size) return;
  const selection=archiveItems().filter(item=>selectedReferences.has(item.id));
  sendingSelection=true;
  selectionStatus.hidden=true;
  updateReferenceSelection();
  try{
    const skipped=await window.addReferencesToBoard(selection);
    clearSelection();
    window.showBoard(skipped);
  }catch(error){
    selectionStatus.textContent=error.message;
    selectionStatus.hidden=false;
  }finally{
    sendingSelection=false;
    updateReferenceSelection();
  }
};

const quickPreview=$('#quickPreview'), quickMedia=$('#quickPreviewMedia');
$('#closeQuickPreview').onclick=()=>quickPreview.close();
quickPreview.addEventListener('close',()=>quickMedia.replaceChildren());
grid.addEventListener('keydown',event=>{
  if(event.code!=='Space'||event.repeat||event.shiftKey||event.metaKey||event.ctrlKey) return;
  const card=event.target.closest('.card');
  if(!card) return;
  const ref=archiveItems().find(item=>item.id===card.dataset.id);
  if(!ref||ref.type==='Аудио'||!/^(https?:\/\/|\/archive\/|\/media\/)/i.test(ref.preview||'')) return;
  event.preventDefault();
  const preview=document.createElement(ref.type==='Видео'?'video':'img');
  if(ref.type==='Видео'){
    preview.controls=true;
    preview.playsInline=true;
  }else preview.alt=ref.title;
  preview.src=ref.preview;
  preview.onerror=()=>{
    quickMedia.textContent=localStorage.getItem('vrw-language')==='en'?'Preview unavailable':'Превью недоступно';
  };
  $('#quickPreviewTitle').textContent=ref.title;
  quickMedia.replaceChildren(preview);
  quickPreview.showModal();
});

document.addEventListener('keydown',event=>{
  if(event.key!=='Escape'||!selectionMode||sendingSelection||$('#libraryPanel').hidden||dialog.open||quickPreview.open) return;
  clearSelection();
  updateReferenceSelection();
});

$('#add').onclick=$('#emptyAdd').onclick=()=>open();
$('#close').onclick=$('#cancel').onclick=()=>dialog.close();
for(const id of ['search','tagFilter']) $('#'+id).addEventListener('input',render);
form.onsubmit=async e=>{e.preventDefault(); let data=Object.fromEntries(new FormData(form)); try{let audio=$('#audioUpload').files[0],file=audio||$('#videoUpload').files[0];if(file){if(file.size>512*1024*1024)throw Error('Файл больше 512 МБ');$('#error').textContent='Загрузка файла…';let upload=await fetch('/api/uploads?name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});if(!upload.ok)throw Error((await upload.json()).error||'Не удалось загрузить видео');data.preview=(await upload.json()).url;data.type=audio?'Аудио':'Видео';form.elements.type.value=data.type;form.elements.preview.value=data.preview;$('#videoUpload').value='';$('#audioUpload').value=''}let res=await fetch('/api/references'+(current?'/'+current:''),{method:current?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}); if(!res.ok) throw Error((await res.json()).error||'Не удалось сохранить'); let saved=await res.json(); if(window.folderSelection&&!current&&saved.id){try{let link=await fetch('/api/folders/'+window.folderSelection.id+'/items',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:'ref:'+saved.id,present:true})});if(!link.ok)throw Error();await window.refreshFolders()}catch(e){alert('Карточка сохранена, но добавить её в папку не удалось.')}} dialog.close(); await load()}catch(err){$('#error').textContent=err.message}};
$('#delete').onclick=async()=>{if(!confirm('Удалить эту карточку? Исходные файлы не будут затронуты.'))return; try{let r=await fetch('/api/references/'+current,{method:'DELETE'});if(!r.ok)throw Error('Не удалось удалить');dialog.close();await load()}catch(e){$('#error').textContent=e.message}};
load().catch(e=>{grid.textContent=e.message});

function setMediaFilter(filter){
  mediaFilter=filter;
  for(const button of document.querySelectorAll('[data-filter]')){
    button.setAttribute('aria-pressed',String(button.dataset.filter===filter));
  }
}

function switchView(nextView){
  window.hideSettings?.();
  window.onLibrarySwitch?.(nextView);
  window.hideStudio?.();
  window.hideBoard?.();
  view=nextView;
  $('#libraryPanel').dataset.view=nextView;
  $('#search').value='';
  $('#tagFilter').value='';
  setMediaFilter('');
  $('#heading').textContent=nextView==='archive'?'Архив':'Коллекции';
  $('#archiveView').classList.toggle('active',nextView==='archive');
  $('#libraryView').classList.toggle('inactive',nextView==='archive');
  render();
}

function updateToolIcon(button, template){
  button.querySelector('svg').replaceWith($(template).content.firstElementChild.cloneNode(true));
}

$('#archiveView').onclick=()=>switchView('archive');
$('#libraryView').onclick=()=>switchView('library');
$('.archive-filters').onclick=event=>{
  const button=event.target.closest('[data-filter]');
  if(!button) return;
  setMediaFilter(button.dataset.filter);
  render();
};
$('#searchToggle').onclick=event=>{
  const button=event.currentTarget;
  const search=$('#archiveSearch');
  search.hidden=!search.hidden;
  button.setAttribute('aria-expanded',String(!search.hidden));
  if(!search.hidden) $('#search').focus();
  else{
    $('#search').value='';
    render();
  }
};
$('#sortToggle').onclick=event=>{
  reverseOrder=!reverseOrder;
  event.currentTarget.setAttribute('aria-pressed',String(reverseOrder));
  render();
};
$('#layoutToggle').onclick=event=>{
  const list=grid.classList.toggle('list');
  const button=event.currentTarget;
  button.setAttribute('aria-pressed',String(list));
  updateToolIcon(button,list?'#listIcon':'#gridIcon');
};
function setSidebarCollapsed(collapsed){
  $('.make-workspace').classList.toggle('sidebar-collapsed',collapsed);
  const button=$('#sidebarToggle');
  button.setAttribute('aria-expanded',String(!collapsed));
  updateToolIcon(button,collapsed?'#expandIcon':'#collapseIcon');
}
setSidebarCollapsed(localStorage.getItem('vrw-sidebar-collapsed')==='true');
$('#sidebarToggle').onclick=()=>{
  const collapsed=$('#sidebarToggle').getAttribute('aria-expanded')==='true';
  setSidebarCollapsed(collapsed);
  localStorage.setItem('vrw-sidebar-collapsed',String(collapsed));
};
$('#tagsToggle').setAttribute('aria-controls','tagControls');
$('#tagsToggle').setAttribute('aria-expanded','false');
$('#tagsToggle').onclick=event=>{
  const controls=$('#tagControls');
  if($('.make-workspace').classList.contains('sidebar-collapsed')){
    setSidebarCollapsed(false);
    localStorage.setItem('vrw-sidebar-collapsed','false');
    controls.hidden=true;
  }
  if(controls.hidden&&$('#libraryPanel').hidden) switchView('archive');
  controls.hidden=!controls.hidden;
  event.currentTarget.setAttribute('aria-expanded',String(!controls.hidden));
  if(!controls.hidden) $('#tagFilter').focus();
};
