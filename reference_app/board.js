(()=>{
const el=s=>document.querySelector(s), viewport=el('#boardViewport'), canvas=el('#boardCanvas'), panel=el('#boardPanel'), picker=el('#picker');
const defaults={brightness:100,contrast:100,saturation:100,grayscale:0,grain:0,hue:0,sepia:0,blur:0,rotation:0,cropLeft:0,cropRight:0,cropTop:0,cropBottom:0,opacity:100,flip:false}; let editorOpen=false;
let items=[], selected=null, scale=1, offset={x:80,y:60}, dirty=false, saving=false, timer, space=false, loadingBoard=null;
const escapeHTML=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function transform(){canvas.style.transform=`translate(${offset.x}px,${offset.y}px) scale(${scale})`;el('#zoomReset').textContent=Math.round(scale*100)+'%'}
function effects(i){let a={...defaults,...i.effects};return `brightness(${a.brightness}%) contrast(${a.contrast}%) saturate(${a.saturation}%) grayscale(${a.grayscale}%) hue-rotate(${a.hue}deg) sepia(${a.sepia}%) blur(${a.blur}px)`}
function syncEditor(){let i=items.find(x=>x.id===selected);el('#photoEditor').hidden=!editorOpen||!i;if(!i)return;let fx={...defaults,...i.effects};for(let key of ['brightness','contrast','saturation','grayscale','grain','hue','sepia','blur','cropLeft','cropRight','cropTop','cropBottom','opacity']){el('#'+key).value=fx[key];el('#'+key+'Value').textContent=fx[key]+(key==='hue'?'°':key==='blur'?' px':'%')}}
function frameGeometry(item,width,height){
  const fx={...defaults,...item.effects};
  const frameWidth=width/(1-(fx.cropLeft+fx.cropRight)/100);
  const frameHeight=height/(1-(fx.cropTop+fx.cropBottom)/100);
  return {width:frameWidth,height:frameHeight,x:-frameWidth*fx.cropLeft/100,y:-frameHeight*fx.cropTop/100};
}
function frameStyle(item){
  const fx={...defaults,...item.effects}, frame=frameGeometry(item,100,100);
  return `width:${frame.width}%;height:${frame.height}%;left:${frame.x}%;top:${frame.y}%;opacity:${fx.opacity/100};transform:scaleX(${fx.flip?-1:1})`;
}
function fitRatio(i){if(!i.naturalW||!i.naturalH)return;let f={...defaults,...i.effects};let ratio=(i.naturalH*(1-(f.cropTop+f.cropBottom)/100))/(i.naturalW*(1-(f.cropLeft+f.cropRight)/100));if((f.rotation||0)%180)ratio=1/ratio;i.h=Math.max(1,Math.round(i.w*ratio))}
function loadBoardMedia(item,forExport=false){
  return new Promise(resolve=>{
    const video=item.kind==='video';
    const media=video?document.createElement('video'):new Image();
    const timeout=setTimeout(()=>finish(null),8000);
    function finish(result){
      clearTimeout(timeout);
      media.onerror=media.onload=media.onloadedmetadata=media.onloadeddata=null;
      if(!result) media.removeAttribute('src');
      resolve(result);
    }
    if(forExport) media.crossOrigin='anonymous';
    if(video){
      media.preload=forExport?'auto':'metadata';
      media.muted=true;
      if(forExport) media.onloadeddata=()=>finish(media);
      else media.onloadedmetadata=()=>finish(media);
    }else media.onload=()=>finish(media);
    media.onerror=()=>finish(null);
    media.src=item.src;
  });
}
async function inspectSize(item){
  const media=await loadBoardMedia(item);
  if(!media) return;
  item.naturalW=media.videoWidth||media.naturalWidth;
  item.naturalH=media.videoHeight||media.naturalHeight;
  fitRatio(item);
}
function paint(){el('#boardExport').disabled=exportingBoard||!items.length;el('#boardSources').disabled=!items.length;canvas.innerHTML=items.map(i=>`<div class="board-item ${i.id===selected?'selected':''}" data-id="${escapeHTML(i.id)}" style="left:${i.x}px;top:${i.y}px;width:${i.w}px;height:${i.h}px"><div class="photo-layer" style="width:${(Number(i.effects?.rotation)||0)%180?i.h:i.w}px;height:${(Number(i.effects?.rotation)||0)%180?i.w:i.h}px;transform:translate(-50%,-50%) rotate(${Number(i.effects?.rotation)||0}deg)">${i.kind==='video'?`<video controls playsinline preload="metadata" src="${escapeHTML(i.src)}" aria-label="${escapeHTML(i.title)}" style="filter:${effects(i)};${frameStyle(i)}"></video>`:`<img draggable="false" src="${escapeHTML(i.src)}" alt="${escapeHTML(i.title)}" style="filter:${effects(i)};${frameStyle(i)}">`}<span class="grain-layer" style="opacity:${Math.max(0,Math.min(1,Number(i.effects?.grain||0)/100))}"></span></div>${i.kind==='video'?'<span class="board-handle" title="Переместить">⋮⋮</span>':''}<button class="board-edit" aria-label="Редактировать изображение">✎</button><button class="board-remove" aria-label="Убрать с доски">×</button><span class="board-resize" aria-label="Изменить размер"></span></div>`).join('');el('#boardEmpty').hidden=items.length>0;syncEditor();transform()}
async function save(){if(saving||!dirty)return;saving=true;dirty=false;el('#boardStatus').textContent='Сохранение…';try{const res=await fetch('/api/board',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(items)});if(!res.ok)throw Error();if(!dirty)el('#boardStatus').textContent='Сохранено'}catch(e){dirty=true;el('#boardStatus').textContent='Не удалось сохранить'}finally{saving=false;if(dirty)timer=setTimeout(save,1000)}}
function changed(){dirty=true;el('#boardStatus').textContent='Изменено';clearTimeout(timer);timer=setTimeout(save,500)}
window.hideBoard=()=>{canvas.querySelectorAll('video').forEach(v=>v.pause());panel.hidden=true;el('#libraryPanel').hidden=false;el('#boardView').classList.remove('active');el('#add').hidden=false};
const boardStatus=el('#boardStatus');
const translateBoard=(ru,en)=>localStorage.getItem('vrw-language')==='en'?en:ru;

function ensureBoard(){
  if(!loadingBoard){
    loadingBoard=(async()=>{
      const response=await fetch('/api/board');
      if(!response.ok) throw new Error(translateBoard('Не удалось открыть доску','Could not open the board'));
      items=await response.json();
      await Promise.all(items.filter(item=>!item.naturalW).map(inspectSize));
      paint();
    })().catch(error=>{loadingBoard=null;throw error;});
  }
  return loadingBoard;
}

window.showBoard=skipped=>{
  window.hideSettings?.();
  window.hideStudio?.();
  el('#libraryPanel').hidden=true;
  panel.hidden=false;
  el('#add').hidden=true;
  el('#boardView').classList.add('active');
  el('#libraryView').classList.add('inactive');
  el('#archiveView').classList.remove('active');
  if(Number.isInteger(skipped)) el('#boardFeedback').textContent=skipped?translateBoard(`Пропущено карточек без превью: ${skipped}`,`Skipped cards without previews: ${skipped}`):'';
};
el('#boardView').onclick=async()=>{
  window.showBoard();
  try{await ensureBoard();}
  catch(error){boardStatus.textContent=error.message;}
};

function canPlaceOnBoard(ref){
  return ref.type!=='Аудио' && /^(https?:\/\/|\/archive\/|\/media\/)/i.test(ref.preview||'');
}

window.addReferencesToBoard=async(selection,center=false)=>{
  const refsWithMedia=selection.filter(canPlaceOnBoard);
  if(!refsWithMedia.length) throw new Error(translateBoard('В выбранных карточках нет фото или видео с превью','The selection has no images or videos with previews'));
  await ensureBoard();
  if(items.length+refsWithMedia.length>1000) throw new Error(translateBoard('На доске помещается до 1000 элементов','The board can hold up to 1,000 items'));
  const additions=refsWithMedia.map(ref=>({
    id:crypto.randomUUID(),
    src:ref.preview,
    title:ref.title,
    sourceUrl:ref.url||'',
    w:220,
    h:220,
    kind:ref.type==='Видео'?'video':'image',
  }));
  for(let start=0;start<additions.length;start+=8){
    await Promise.all(additions.slice(start,start+8).map(inspectSize));
  }
  if(items.length+additions.length>1000) throw new Error(translateBoard('На доске помещается до 1000 элементов','The board can hold up to 1,000 items'));
  const columns=Math.min(additions.length,4);
  const left=items.length?Math.min(...items.map(item=>item.x)):0;
  let rowTop=items.length?Math.max(...items.map(item=>item.y+item.h))+24:0;
  for(let index=0;index<additions.length;index+=columns){
    const row=additions.slice(index,index+columns);
    row.forEach((item,column)=>{
      item.x=left+column*244;
      item.y=rowTop;
    });
    rowTop+=Math.max(...row.map(item=>item.h))+24;
  }
  if(center&&additions.length===1){
    const item=additions[0];
    item.x=Math.round((viewport.clientWidth/2-offset.x)/scale-item.w/2);
    item.y=Math.round((viewport.clientHeight/2-offset.y)/scale-item.h/2);
  }
  items.push(...additions);
  selected=additions.at(-1).id;
  if(!center){
    scale=1;
    offset={x:60-additions[0].x,y:60-additions[0].y};
  }
  paint();
  changed();
  return selection.length-additions.length;
};

function showPicker(){let all=[...refs,...archive].filter(canPlaceOnBoard);let q=el('#pickerSearch').value.toLocaleLowerCase().trim();el('#pickerGrid').innerHTML=all.filter(r=>[r.title,r.author,r.tags].some(v=>String(v||'').toLocaleLowerCase().includes(q))).map(r=>`<button class="picker-item" data-ref="${escapeHTML(r.id)}">${r.type==='Видео'?`<video preload="metadata" muted playsinline src="${escapeHTML(r.preview)}"></video>`:`<img loading="lazy" src="${escapeHTML(r.preview)}" alt="">`}<span>${escapeHTML(r.title)}</span></button>`).join('')}
el('#boardAdd').onclick=()=>{el('#pickerSearch').value='';el('#pickerStatus').textContent='';showPicker();picker.showModal()};el('#pickerClose').onclick=()=>picker.close();el('#pickerSearch').oninput=showPicker;
el('#pickerGrid').onclick=async event=>{
  const button=event.target.closest('[data-ref]');
  const ref=button&&[...refs,...archive].find(item=>item.id===button.dataset.ref);
  if(!ref||button.disabled) return;
  button.disabled=true;
  try{
    await window.addReferencesToBoard([ref],true);
    picker.close();
  }catch(error){
    el('#pickerStatus').textContent=error.message;
  }finally{
    button.disabled=false;
  }
};
viewport.addEventListener('pointerdown',e=>{if(e.target.tagName==='VIDEO')return;let node=e.target.closest('.board-item');if(e.target.closest('.board-edit')){selected=node.dataset.id;editorOpen=true;paint();return}if(e.target.closest('.board-remove')){let i=items.findIndex(x=>x.id===node.dataset.id);if(i>=0){items.splice(i,1);selected=null;paint();changed()}return}let item=node&&items.find(x=>x.id===node.dataset.id);let mode=space||!item?'pan':e.target.closest('.board-resize')?'resize':'move';if(item&&!space){selected=item.id;paint()}else if(!item){selected=null;paint()}let start={x:e.clientX,y:e.clientY,ox:offset.x,oy:offset.y,ix:item?.x,iy:item?.y,w:item?.w,h:item?.h};viewport.setPointerCapture(e.pointerId);function move(ev){let dx=ev.clientX-start.x,dy=ev.clientY-start.y;if(mode==='pan'){offset.x=start.ox+dx;offset.y=start.oy+dy;transform()}else{if(mode==='move'){item.x=Math.round(start.ix+dx/scale);item.y=Math.round(start.iy+dy/scale)}else{let factor=Math.max(.3,(start.w+dx/scale)/start.w);item.w=Math.round(start.w*factor);item.h=Math.round(start.h*factor)}let n=canvas.querySelector(`[data-id="${item.id}"]`);Object.assign(n.style,{left:item.x+'px',top:item.y+'px',width:item.w+'px',height:item.h+'px'});let layer=n.querySelector('.photo-layer');let turn=(item.effects?.rotation||0)%180;layer.style.width=(turn?item.h:item.w)+'px';layer.style.height=(turn?item.w:item.h)+'px'}}function up(){viewport.removeEventListener('pointermove',move);viewport.removeEventListener('pointerup',up);viewport.removeEventListener('pointercancel',up);if(mode!=='pan')changed()}viewport.addEventListener('pointermove',move);viewport.addEventListener('pointerup',up);viewport.addEventListener('pointercancel',up)});

for(const key of ['brightness','contrast','saturation','grayscale','grain','hue','sepia','blur','cropLeft','cropRight','cropTop','cropBottom','opacity'])el('#'+key).addEventListener('input',e=>{let item=items.find(x=>x.id===selected);if(!item)return;item.effects={...defaults,...item.effects,[key]:Number(e.target.value)};let img=canvas.querySelector('.board-item.selected img, .board-item.selected video');if(key.startsWith('crop')){fitRatio(item);paint()}else if(img){img.style.filter=effects(item);img.style.cssText+=';'+frameStyle(item)}let grain=canvas.querySelector('.board-item.selected .grain-layer');if(grain)grain.style.opacity=item.effects.grain/100;el('#'+key+'Value').textContent=e.target.value+(key==='hue'?'°':key==='blur'?' px':'%');changed()});
function rotate(delta){let item=items.find(x=>x.id===selected);if(!item)return;item.effects={...defaults,...item.effects,rotation:((item.effects?.rotation||0)+delta+360)%360};[item.w,item.h]=[item.h,item.w];paint();changed()}
el('#flipPhoto').onclick=()=>{let item=items.find(x=>x.id===selected);if(item){item.effects={...defaults,...item.effects,flip:!item.effects?.flip};paint();changed()}};
el('#rotateLeft').onclick=()=>rotate(-90);el('#rotateRight').onclick=()=>rotate(90);el('#resetPhoto').onclick=()=>{let item=items.find(x=>x.id===selected);if(item){if((item.effects?.rotation||0)%180)[item.w,item.h]=[item.h,item.w];item.effects={...defaults};fitRatio(item);paint();changed()}};el('#editorClose').onclick=()=>{editorOpen=false;syncEditor()};

function downloadBoardFile(blob,name){
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');
  link.href=url;
  link.download=name;
  link.click();
  setTimeout(()=>URL.revokeObjectURL(url),30000);
}

async function loadExportGrain(context){
  const layer=canvas.querySelector('.grain-layer');
  const css=layer&&getComputedStyle(layer).backgroundImage;
  const src=css?.match(/^url\("(data:image\/svg\+xml,[^"]+)"\)$/)?.[1];
  if(!src) return null;
  const image=await loadBoardMedia({src});
  if(!image) return null;
  const square=document.createElement('canvas');
  square.width=square.height=160;
  square.getContext('2d').drawImage(image,0,0,160,160);
  return context.createPattern(square,'repeat');
}

function drawExportItem(context,item,media,grain){
  const fx={...defaults,...item.effects};
  const turned=fx.rotation%180!==0;
  const width=turned?item.h:item.w;
  const height=turned?item.w:item.h;
  context.save();
  try{
    context.translate(item.x+item.w/2,item.y+item.h/2);
    context.rotate(fx.rotation*Math.PI/180);
    context.translate(-width/2,-height/2);
    context.beginPath();
    context.rect(0,0,width,height);
    context.clip();
    if(!media){
      context.fillStyle='#292929';
      context.fillRect(0,0,width,height);
      context.fillStyle='#d0d0d0';
      context.font='13px sans-serif';
      context.fillText(item.title||'',10,22,Math.max(1,width-20));
      return;
    }
    const frame=frameGeometry(item,width,height);
    context.save();
    try{
      context.globalAlpha=fx.opacity/100;
      if('filter' in context) context.filter=effects(item);
      context.translate(frame.x+(fx.flip?frame.width:0),frame.y);
      context.scale(fx.flip?-1:1,1);
      context.drawImage(media,0,0,frame.width,frame.height);
    }finally{
      context.restore();
    }
    if(grain&&fx.grain>0){
      context.globalAlpha=fx.grain/100;
      context.globalCompositeOperation='overlay';
      context.fillStyle=grain;
      context.fillRect(0,0,width,height);
    }
  }finally{
    context.restore();
  }
}

let exportingBoard=false;
const exportButton=el('#boardExport');
const feedback=el('#boardFeedback');

exportButton.onclick=async()=>{
  if(!items.length||exportingBoard) return;
  exportingBoard=true;
  exportButton.disabled=true;
  feedback.textContent=translateBoard('Готовим PNG…','Preparing PNG…');
  try{
    const snapshot=structuredClone(items);
    const left=Math.min(...snapshot.map(item=>item.x))-32;
    const top=Math.min(...snapshot.map(item=>item.y))-32;
    const width=Math.max(...snapshot.map(item=>item.x+item.w))+32-left;
    const height=Math.max(...snapshot.map(item=>item.y+item.h))+32-top;
    const ratio=Math.min(2,4096/Math.max(width,height));
    const output=document.createElement('canvas');
    output.width=Math.max(1,Math.ceil(width*ratio));
    output.height=Math.max(1,Math.ceil(height*ratio));
    const context=output.getContext('2d');
    context.fillStyle='#101010';
    context.fillRect(0,0,output.width,output.height);
    context.scale(ratio,ratio);
    context.translate(-left,-top);
    const grain=snapshot.some(item=>item.effects?.grain>0)?await loadExportGrain(context):null;
    let missing=0;
    for(let start=0;start<snapshot.length;start+=8){
      const group=snapshot.slice(start,start+8);
      const media=await Promise.all(group.map(item=>loadBoardMedia(item,true)));
      group.forEach((item,index)=>{
        if(!media[index]) missing+=1;
        drawExportItem(context,item,media[index],grain);
      });
    }
    const blob=await new Promise(resolve=>output.toBlob(resolve,'image/png'));
    if(!blob) throw new Error();
    downloadBoardFile(blob,'moodboard.png');
    feedback.textContent=missing
      ?translateBoard(`На PNG заменены заглушками: ${missing}`,`PNG placeholders: ${missing}`)
      :translateBoard('PNG готов','PNG ready');
  }catch{
    feedback.textContent=translateBoard('Не удалось экспортировать PNG','Could not export PNG');
  }finally{
    exportingBoard=false;
    exportButton.disabled=!items.length;
  }
};

el('#boardSources').onclick=()=>{
  if(!items.length) return;
  const originalSources=new Map([...archive,...refs].filter(ref=>ref.url).map(ref=>[ref.preview,ref.url]));
  const lines=items.map(item=>{
    const url=[item.sourceUrl,originalSources.get(item.src),item.src].find(source=>/^https?:\/\//i.test(source||''));
    const title=String(item.title||'').replace(/\s+/g,' ').trim()||translateBoard('Без названия','Untitled');
    return title+'\n'+(url||translateBoard('Локальный файл','Local file'));
  });
  downloadBoardFile(new Blob([lines.join('\n\n')+'\n'],{type:'text/plain;charset=utf-8'}),'moodboard-sources.txt');
};

function zoom(next){let old=scale;scale=Math.min(3,Math.max(.25,next));let cx=viewport.clientWidth/2,cy=viewport.clientHeight/2;offset.x=cx-(cx-offset.x)*scale/old;offset.y=cy-(cy-offset.y)*scale/old;transform()}
el('#zoomIn').onclick=()=>zoom(scale*1.2);el('#zoomOut').onclick=()=>zoom(scale/1.2);el('#zoomReset').onclick=()=>zoom(1);
viewport.addEventListener('wheel',e=>{e.preventDefault();if(e.ctrlKey||e.metaKey)zoom(scale*Math.exp(-e.deltaY*.002));else{offset.x-=e.deltaX;offset.y-=e.deltaY;transform()}},{passive:false});
document.addEventListener('keydown',e=>{if(panel.hidden||/INPUT|TEXTAREA|SELECT|BUTTON/.test(e.target.tagName)||picker.open)return;if(e.code==='Space'){space=true;e.preventDefault()}if((e.key==='Delete'||e.key==='Backspace')&&selected){items=items.filter(i=>i.id!==selected);selected=null;paint();changed()}});document.addEventListener('keyup',e=>{if(e.code==='Space')space=false});window.addEventListener('blur',()=>space=false);
})();
