"""Copy a previously used workspace once, then start the desktop data engine."""
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory


def migrate(source, target):
    if source is None:
        return
    previous = source / 'references.sqlite3'
    current = target / 'references.sqlite3'
    if current.exists() or not previous.is_file() or previous.resolve() == current.resolve():
        return
    target.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='migration-', dir=target) as staging:
        snapshot = Path(staging) / current.name
        with closing(sqlite3.connect(previous.resolve().as_uri() + '?mode=ro', uri=True)) as origin:
            with closing(sqlite3.connect(snapshot)) as backup:
                origin.backup(backup)
        uploads = source / 'uploads'
        if uploads.is_dir() and not (target / 'uploads').exists():
            # Ignore symlinks and hidden files from copied or user-selected workspaces.
            def exclude_unsafe(directory, names):
                return [name for name in names if name.startswith('.') or (Path(directory) / name).is_symlink()]
            shutil.copytree(uploads, Path(staging) / 'uploads', ignore=exclude_unsafe)
            (Path(staging) / 'uploads').rename(target / 'uploads')
        snapshot.rename(current)


def main():
    import sys
    import json
    import io
    import uuid

    target = Path(os.environ['REFERENCE_DATA_DIR'])
    initial = os.environ.pop('REFERENCE_PREVIOUS_WORKSPACE', '')
    migrate(Path(initial) if initial else None, target)
    import server
    import workflow

    def presentation(item):
        path = server.resolve_media(item.get('preview', ''))
        return {**item, 'filePath': str(path) if path else ''}

    def call(method, path, body=None):
        if not path.startswith('/api/') or method not in ('GET','POST','PUT','DELETE'):
            raise ValueError('Unsupported desktop operation')
        request = object.__new__(server.Handler)
        request.command = method
        request.path = path
        encoded = json.dumps(body).encode() if body is not None else b''
        request.rfile = io.BytesIO(encoded)
        request.headers = {'Content-Length':str(len(encoded))}
        result = []
        request.send = lambda code, payload, content=None: result.append((code,json.loads(payload)))
        getattr(request, 'do_' + method)()
        status, data = result[0]
        if status>=400:
            raise ValueError(data.get('error') or f'Ошибка операции ({status})')
        return data

    def dispatch(request):
        operation = request.get('op')
        if operation=='api':
            return call(request['method'],request['path'],request.get('body'))
        if operation=='catalog':
            return [presentation(item) for item in call('GET','/api/references')+server.archive_entries()]
        if operation=='board':
            return [presentation({**item,'preview':item.get('src','')}) for item in call('GET','/api/board')]
        if operation=='resolve':
            return presentation({'preview':request['preview']})
        if operation=='import':
            source = Path(request['file']).expanduser()
            extension = source.suffix.lower()
            if extension not in workflow.IMAGE_EXTENSIONS | workflow.VIDEO_EXTENSIONS | {'.mp3'} or not source.is_file():
                raise ValueError('Формат файла не поддерживается')
            if not 0<source.stat().st_size<=512*1024*1024:
                raise ValueError('Поддерживаются файлы до 512 МБ')
            server.UPLOADS.mkdir(exist_ok=True)
            output = server.UPLOADS/(uuid.uuid4().hex+extension)
            try:
                with source.open('rb') as original, output.open('xb') as destination:
                    shutil.copyfileobj(original,destination)
                kind='Видео' if extension in workflow.VIDEO_EXTENSIONS else 'Аудио' if extension=='.mp3' else 'Фото'
                ref={'title':request.get('title') or source.stem, 'preview':'/media/'+output.name,
                     'type':kind,'url':request.get('source') or '', 'description':request.get('description') or ''}
                from datetime import date
                ref['added']=date.today().isoformat()
                result=call('POST','/api/references',ref)
            except BaseException:
                output.unlink(missing_ok=True)
                raise
            return presentation({**ref,**result})
        if operation=='search':
            result=call('POST','/api/workflow/search',request['body'])
            return {**result,'items':[presentation(ref) for ref in result['items']]}
        if operation=='clip':
            from datetime import date
            preview = call('POST','/api/workflow/clip',request['body'])['url']
            ref = {'preview':preview,'title':request.get('title') or 'Фрагмент',
                   'url':request.get('source') or '', 'type':'Видео','added':date.today().isoformat()}
            try:
                return presentation({**ref,**call('POST','/api/references',ref)})
            except Exception:
                output = server.resolve_media(preview)
                if output: output.unlink(missing_ok=True)
                raise
        raise ValueError('Unsupported desktop operation')

    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = {'ok':True,'result':dispatch(request)}
        except Exception as error:
            response = {'ok':False,'error':str(error)}
        print(json.dumps(response,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
