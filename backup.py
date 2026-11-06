"""Private local state archives; never upload archives or restore executable service units."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile
import uuid

UNITS = ['hermes-dashboard', 'hermes-gateway', 'opencode-web', '9router', 'hermin']
SKIP_DIRS = {'node_modules', '__pycache__', '.git', '.aws', '.codex', '.agents',
             'installs', 'tools', 'bin', '.venv', 'venv', '.uv-cache', '.uv-python',
             'cache', '.cache', 'audio_cache', 'image_cache', 'logs', 'backups',
             'runtime', 'headroom'}


def locations(root, home):
    return {'hermes': root/'hermes/data', 'router': root/'9router/data',
            'opencode-config': home/'.config/opencode', 'opencode-home': home/'.opencode',
            'opencode-data': home/'.local/share/opencode', 'opencode-state': home/'.local/state/opencode',
            'shared-skills': home/'.agents/skills', 'claude-skills': home/'.claude/skills'}


@contextmanager
def stopped_services(enabled=True):
    active = []
    if enabled:
        subprocess.run(['systemctl','--user','show-environment'], check=True, capture_output=True)
        for unit in UNITS:
            if subprocess.run(['systemctl','--user','is-active','--quiet',unit]).returncode == 0:
                active.append(unit)
    try:
        for unit in active:
            subprocess.run(['systemctl','--user','stop',unit], check=True, timeout=120)
        yield
    finally:
        failures = []
        for unit in reversed(active):
            if subprocess.run(['systemctl','--user','start',unit], timeout=120).returncode:
                failures.append(unit)
        if failures:
            raise RuntimeError('Data tersimpan, tetapi layanan gagal dinyalakan: '+', '.join(failures))


def walk(folder, ancestors=frozenset()):
    real = folder.resolve()
    if real in ancestors:
        return
    for path in sorted(folder.iterdir()):
        if path.name in SKIP_DIRS or path.name.endswith(('.lock','.pid','.sock','-wal','-shm')):
            continue
        if path.is_dir():
            yield from walk(path, ancestors | {real})
        elif path.is_file():
            yield path


def backup(root, home, output=None):
    root, home = Path(root), Path(home)
    output = Path(output) if output else root/'hermin/backups'/datetime.now(timezone.utc).strftime('hermin-state-%Y%m%d-%H%M%S-%f.tar.gz')
    output = output.expanduser().absolute()
    if not output.name.endswith('.tar.gz'):
        raise ValueError('Gunakan nama arsip .tar.gz agar selalu dikecualikan dari Git.')
    for path in locations(root, home).values():
        if output.resolve().is_relative_to(path.resolve()):
            raise ValueError('Simpan backup di luar direktori data yang diarsipkan.')
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    manifest = {'format':1,'version':'0.0.1-beta','root':str(root),'home':str(home),'files':{}}
    try:
        with os.fdopen(fd,'wb') as target, tarfile.open(fileobj=target,mode='w:gz',dereference=True) as archive:
            for component, folder in locations(root,home).items():
                if not folder.is_dir():continue
                for path in walk(folder):
                    name = 'payload/'+component+'/'+path.relative_to(folder).as_posix()
                    info = archive.gettarinfo(str(path.resolve()),arcname=name)
                    info.uid=info.gid=0;info.uname=info.gname='';info.mode=0o600
                    if not info.isfile():raise ValueError('Backup hanya menerima file biasa.')
                    with path.open('rb') as source:
                        digest=hashlib.file_digest(source,'sha256').hexdigest();source.seek(0)
                        archive.addfile(info,source)
                    manifest['files'][name]={'sha256':digest,'size':info.size,'executable':bool(path.stat().st_mode & 0o100)}
            if not manifest['files']:raise ValueError('Tidak ada data yang bisa dibackup.')
            import io
            data=json.dumps(manifest,indent=2).encode();info=tarfile.TarInfo('manifest.json');info.size=len(data);info.mode=0o600
            archive.addfile(info,io.BytesIO(data))
        return output
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def validate_extract(archive_path, stage):
    with tarfile.open(archive_path,'r:gz') as archive:
        members=archive.getmembers()
        if len(members)>100000:raise ValueError('Backup terlalu banyak file.')
        names=[m.name for m in members]
        if len(names)!=len(set(names)):raise ValueError('Nama file duplikat dalam backup.')
        if any(not m.isfile() or m.size<0 for m in members):raise ValueError('Link atau file khusus dalam backup ditolak.')
        if sum(m.size for m in members)>20*1024**3:raise ValueError('Backup melebihi batas ekstraksi 20 GiB.')
        meta=archive.getmember('manifest.json')
        if meta.size>32*1024**2:raise ValueError('Manifest terlalu besar.')
        manifest=json.load(archive.extractfile(meta))
        if not isinstance(manifest,dict) or manifest.get('format')!=1 or not isinstance(manifest.get('files'),dict):raise ValueError('Format backup tidak dikenal.')
        if set(names)!={'manifest.json',*manifest['files']}:raise ValueError('Manifest tidak sesuai isi arsip.')
        for old in ('home','root'):
            value=manifest.get(old)
            if not isinstance(value,str) or not value.startswith('/') or value=='/':raise ValueError('Lokasi asal backup tidak valid.')
        components=set(locations(Path('/stack'),Path('/home/user')))
        for member in members:
            if member.name=='manifest.json':continue
            path=PurePosixPath(member.name)
            if path.as_posix()!=member.name or path.is_absolute() or '..' in path.parts or len(path.parts)<3 or path.parts[0]!='payload' or path.parts[1] not in components:
                raise ValueError('Path dalam backup tidak aman.')
            expected=manifest['files'][member.name]
            if expected['size']!=member.size:raise ValueError('Ukuran file tidak sesuai manifest.')
            target=stage.joinpath(*path.parts);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with archive.extractfile(member) as source,target.open('wb') as dest:
                shutil.copyfileobj(source,dest)
            target.chmod(0o600)
            with target.open('rb') as saved:
                if hashlib.file_digest(saved,'sha256').hexdigest()!=expected['sha256']:raise ValueError('Checksum backup gagal.')
            target.chmod(0o700 if expected.get('executable') else 0o600)
        return manifest


def restore(root, home, archive_path, overwrite=False):
    root, home = Path(root),Path(home)
    root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.hermin-restore-',dir=root) as work:
        stage=Path(work);manifest=validate_extract(archive_path,stage)
        plan=[]
        for component, folder in locations(root,home).items():
            source=stage/'payload'/component
            if not source.exists():continue
            base=folder.resolve()
            for item in source.rglob('*'):
                if not item.is_file():continue
                dest=base/item.relative_to(source)
                if dest.is_symlink() or not dest.resolve().is_relative_to(base):raise ValueError('Tujuan restore mengarah ke symlink di luar direktori data.')
                if dest.exists() and not overwrite:raise ValueError('File sudah ada; gunakan --overwrite setelah meninjau backup: '+str(dest))
                plan.append((item,dest))
        if not plan:raise ValueError('Backup tidak berisi data.')
        recovery=root/'hermin/backups'/('pre-restore-'+uuid.uuid4().hex)
        recovery.mkdir(parents=True,mode=0o700)
        journal={}
        try:
            # WAL from an older database must never be replayed into a restored DB.
            targets={dest for _,dest in plan}
            targets |= {Path(str(dest)+suffix) for _,dest in plan for suffix in ('-wal','-shm') if Path(str(dest)+suffix).exists()}
            for index,dest in enumerate(sorted(targets)):
                if dest.is_symlink() or (dest.exists() and not dest.is_file()):raise ValueError('Tujuan bukan file biasa: '+str(dest))
                saved=recovery/str(index) if dest.exists() else None
                if saved:shutil.copy2(dest,saved);saved.chmod(0o600)
                journal[dest]=saved
            (recovery/'manifest.json').write_text(json.dumps({str(k):str(v) if v else None for k,v in journal.items()},indent=2))
            for item,dest in plan:
                dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                if item.suffix in ('.json','.jsonc','.yaml','.yml','.md','.env') or item.name=='.env':
                    try:
                        text=item.read_text();text=text.replace(manifest['root'],str(root)).replace(manifest['home'],str(home));item.write_text(text)
                    except UnicodeError:pass
                os.replace(item,dest)
            for dest in targets-{dest for _,dest in plan}:dest.unlink(missing_ok=True)
        except BaseException:
            for dest,saved in journal.items():
                if saved:shutil.copy2(saved,dest)
                else:dest.unlink(missing_ok=True)
            raise
        return recovery,len(plan)
