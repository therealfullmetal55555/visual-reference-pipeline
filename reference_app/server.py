import json, sqlite3, os, uuid, mimetypes, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote, parse_qs
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DB=ROOT/'references.sqlite3'
FIELDS=['title','url','author','type','preview','description','hook','composition','light','color','typography','texture','editing','camera','tags','ideas','added']
def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
with db() as c:
 c.execute('CREATE TABLE IF NOT EXISTS folders (id TEXT PRIMARY KEY, name TEXT NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS folder_items (folder_id TEXT NOT NULL, ref_key TEXT NOT NULL, PRIMARY KEY(folder_id, ref_key))')
 c.execute('CREATE TABLE IF NOT EXISTS board (id INTEGER PRIMARY KEY CHECK (id=1), data TEXT NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS refs (id TEXT PRIMARY KEY, '+', '.join('"'+f+'" TEXT NOT NULL DEFAULT \'\'' for f in FIELDS)+')')
class Handler(BaseHTTPRequestHandler):
 def send(self, status, data, content='application/json; charset=utf-8'):
  self.send_response(status); self.send_header('Content-Type',content); self.send_header('Content-Length',str(len(data))); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(data)
 def js(self,status,obj): self.send(status,json.dumps(obj,ensure_ascii=False).encode())
 def video_file(self, f):
  size=f.stat().st_size; start=0; end=size-1; status=200
  value=self.headers.get('Range')
  if value:
   match=re.fullmatch(r'bytes=(\d*)-(\d*)',value.strip())
   if not match or not (match.group(1) or match.group(2)):
    self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.end_headers(); return
   if match.group(1): start=int(match.group(1)); end=int(match.group(2)) if match.group(2) else end
   else: start=max(0,size-int(match.group(2)))
   if start>=size or end<start:
    self.send_response(416); self.send_header('Content-Range',f'bytes */{size}'); self.end_headers(); return
   end=min(end,size-1); status=206
  self.send_response(status); self.send_header('Content-Type',mimetypes.guess_type(f.name)[0] or 'application/octet-stream'); self.send_header('Accept-Ranges','bytes'); self.send_header('Content-Length',str(end-start+1)); self.send_header('X-Content-Type-Options','nosniff')
  if status==206: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  self.end_headers()
  try:
   with f.open('rb') as source:
    source.seek(start); remaining=end-start+1
    while remaining:
     chunk=source.read(min(1024*1024,remaining))
     if not chunk: break
     self.wfile.write(chunk); remaining-=len(chunk)
  except (BrokenPipeError,ConnectionResetError): pass
 def do_HEAD(self):
  self.do_GET()
 def do_GET(self):
  path=urlparse(self.path).path
  if path=='/api/folders':
   with db() as c:
    folders=[dict(r) for r in c.execute('SELECT * FROM folders ORDER BY name COLLATE NOCASE')]
    for f in folders: f['items']=[r[0] for r in c.execute('SELECT ref_key FROM folder_items WHERE folder_id=?',(f['id'],))]
   self.js(200,folders); return
  if path=='/api/board':
   with db() as c: row=c.execute('SELECT data FROM board WHERE id=1').fetchone()
   self.js(200,json.loads(row['data']) if row else []); return
  if path=='/api/archive':
   records=[]
   archive_dir=None
   for cand in (ROOT.parent/'archive_index.json', ROOT/'archive_index.json', Path.home()/'Desktop'/'instagram_archive'/'archive_index.json'):
    if cand.is_file():
     try:
      with cand.open(encoding='utf-8') as f: records=json.load(f)
      archive_dir=cand.parent; break
     except Exception: pass
   result=[]
   for i, r in enumerate(records):
    rel=r.get('relative_path') or r.get('local_path') or ''
    found=False
    for base in ([archive_dir] if archive_dir else []) + [ROOT.parent, ROOT, Path.home()/'Desktop'/'instagram_archive']:
     if base and (base/rel).is_file(): found=True; break
    if not rel.startswith('images/') or not found: continue
    result.append({'id':'archive:'+str(i),'title':r.get('title') or r.get('file') or 'Без названия','url':r.get('canonical_url') or r.get('source_url') or r.get('instagram_url') or '', 'author':r.get('author') or '', 'type':'Фото','preview':'/archive/'+rel,'description':r.get('summary') or r.get('observation') or '', 'hook':'','composition':'','light':'','color':'','typography':'','texture':'','editing':'','camera':'','tags':', '.join(r.get('tags') or []),'ideas':'','added':'','archived':True})
   self.js(200,result); return
  if path=='/api/references':
   with db() as c: self.js(200,[dict(r) for r in c.execute('SELECT * FROM refs ORDER BY added DESC, rowid DESC')]); return
  if path in ('/','/app.js','/style.css','/board.js','/studio.js','/workspace.js','/clover-original.jpg','/ballerina-original.jpg'):
   f=ROOT/('index.html' if path=='/' else path[1:]); self.send(200,f.read_bytes(),mimetypes.guess_type(f.name)[0]+'; charset=utf-8'); return
  if path.startswith('/media/'):
   base=(ROOT/'uploads').resolve(); f=(base/unquote(path[len('/media/'):])).resolve()
   if f.is_relative_to(base) and f.is_file(): self.video_file(f); return
   return self.js(404,{'error':'Не найдено'})
  if path.startswith('/fonts/'):
   f=(ROOT/path.lstrip('/')).resolve()
   if f.is_relative_to(ROOT/'fonts') and f.is_file(): self.send(200,f.read_bytes(),mimetypes.guess_type(f.name)[0] or 'application/octet-stream'); return
  if path.startswith('/archive/'):
   rel=unquote(path[len('/archive/'):])
   for base in (ROOT.parent, ROOT, Path.home()/'Desktop'/'instagram_archive'):
    b=base.resolve(); f=(b/rel).resolve()
    if (f.is_relative_to(b/'images') or f.is_relative_to(b)) and f.is_file():
     self.send(200,f.read_bytes(),mimetypes.guess_type(f.name)[0] or 'application/octet-stream'); return
   return self.js(404,{'error':'Не найдено'})
  self.js(404,{'error':'Не найдено'})
 def body(self):
  n=int(self.headers.get('Content-Length','0'))
  if n>100000: raise ValueError('Слишком большая карточка')
  d=json.loads(self.rfile.read(n)); v={f:str(d.get(f,'')).strip() for f in FIELDS}
  if not v['title']: raise ValueError('Укажите название')
  if v['type'] not in ('Фото','Видео','Аудио','Карусель','Сайт','Другое'): raise ValueError('Выберите тип')
  return v
 def read_json(self):
  n=int(self.headers.get('Content-Length','0'))
  if n>100000: raise ValueError('Request too large')
  data=json.loads(self.rfile.read(n))
  if not isinstance(data,dict): raise ValueError('Invalid request')
  return data
 def do_POST(self):
  if urlparse(self.path).path=='/api/uploads':
   try:
    suffix=Path(parse_qs(urlparse(self.path).query).get('name',[''])[0]).suffix.lower()
    if suffix not in ('.mp4','.webm','.mov','.ogv','.mp3'): raise ValueError('Поддерживаются MP3, MP4, WebM, MOV и OGV')
    size=int(self.headers.get('Content-Length','0'))
    if size<=0 or size>512*1024*1024: raise ValueError('Размер файла должен быть от 1 байта до 512 МБ')
    folder=ROOT/'uploads'; folder.mkdir(exist_ok=True); target=folder/(str(uuid.uuid4())+suffix)
    try:
     with target.open('xb') as out:
      remaining=size
      while remaining:
       chunk=self.rfile.read(min(1024*1024,remaining))
       if not chunk: raise ValueError('Загрузка прервалась')
       out.write(chunk); remaining-=len(chunk)
    except Exception:
     target.unlink(missing_ok=True); raise
    return self.js(201,{'url':'/media/'+target.name})
   except (OSError,ValueError) as e: return self.js(400,{'error':str(e)})
  if self.path=='/api/folders':
   try:
    name=self.read_json().get('name','').strip()
    if not name or len(name)>80: raise ValueError('Invalid name')
    ident=str(uuid.uuid4())
    with db() as c: c.execute('INSERT INTO folders VALUES (?,?)',(ident,name))
    return self.js(201,{'id':ident})
   except (ValueError,TypeError,AttributeError) as e: return self.js(400,{'error':str(e)})
  if self.path!='/api/references': return self.js(404,{})
  try:
   v=self.body(); ident=str(uuid.uuid4())
   with db() as c: c.execute('INSERT INTO refs (id,'+','.join('"'+f+'"' for f in FIELDS)+') VALUES ('+','.join('?' for _ in range(len(FIELDS)+1))+')',[ident]+list(v.values()))
   self.js(201,{'id':ident})
  except (ValueError,TypeError,json.JSONDecodeError) as e: self.js(400,{'error':str(e)})
 def do_PUT(self):
  if self.path.startswith('/api/folders/'):
   try:
    ident=self.path.split('/')[3]; data=self.read_json()
    with db() as c:
     if not c.execute('SELECT 1 FROM folders WHERE id=?',(ident,)).fetchone(): return self.js(404,{'error':'Not found'})
     if self.path.endswith('/items'):
      key=data.get('key'); present=data.get('present')
      if not isinstance(key,str) or not key or len(key)>2000 or not isinstance(present,bool): raise ValueError('Invalid item')
      if present: c.execute('INSERT OR IGNORE INTO folder_items VALUES (?,?)',(ident,key))
      else: c.execute('DELETE FROM folder_items WHERE folder_id=? AND ref_key=?',(ident,key))
     else:
      name=data.get('name','').strip()
      if not name or len(name)>80: raise ValueError('Invalid name')
      c.execute('UPDATE folders SET name=? WHERE id=?',(name,ident))
    return self.js(200,{'ok':True})
   except (ValueError,TypeError,AttributeError) as e: return self.js(400,{'error':str(e)})
  if self.path=='/api/board':
   try:
    n=int(self.headers.get('Content-Length','0'))
    if n>1000000: raise ValueError('Доска слишком большая')
    data=json.loads(self.rfile.read(n))
    if not isinstance(data,list) or len(data)>1000: raise ValueError('Неверные данные доски')
    with db() as c: c.execute('INSERT INTO board (id,data) VALUES (1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(json.dumps(data,ensure_ascii=False),))
    return self.js(200,{'ok':True})
   except (ValueError,TypeError,json.JSONDecodeError) as e: return self.js(400,{'error':str(e)})
  ident=self.path.removeprefix('/api/references/')
  try:
   v=self.body()
   with db() as c: cur=c.execute('UPDATE refs SET '+','.join('"'+f+'"=?' for f in FIELDS)+' WHERE id=?',list(v.values())+[ident])
   self.js(200 if cur.rowcount else 404,{'ok':bool(cur.rowcount)})
  except (ValueError,TypeError,json.JSONDecodeError) as e: self.js(400,{'error':str(e)})
 def do_DELETE(self):
  if self.path.startswith('/api/folders/'):
   ident=self.path.split('/')[3]
   with db() as c:
    c.execute('DELETE FROM folder_items WHERE folder_id=?',(ident,)); cur=c.execute('DELETE FROM folders WHERE id=?',(ident,))
   return self.js(200 if cur.rowcount else 404,{'ok':bool(cur.rowcount)})
  ident=self.path.removeprefix('/api/references/')
  with db() as c: cur=c.execute('DELETE FROM refs WHERE id=?',(ident,))
  self.js(200 if cur.rowcount else 404,{'ok':bool(cur.rowcount)})
if __name__=='__main__':
 port=int(os.environ.get('PORT','8765')); print(f'http://127.0.0.1:{port}',flush=True); ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
