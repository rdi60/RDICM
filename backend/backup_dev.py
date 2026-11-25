"""Offline development backup + integrity verification. NOT a production DR system.
Run: python backup_dev.py create /safe/offline/backup-dir
     python backup_dev.py verify /safe/offline/backup-dir/backup_... 
"""
import argparse, hashlib, json, os, shutil, sqlite3, sys, tempfile
from pathlib import Path
from datetime import datetime, timezone
from app import DB, DOCUMENT_ROOT

def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def create(destination):
 if not DB.is_file():raise RuntimeError('Database not initialized; no backup created')
 dest=Path(destination).expanduser().resolve()
 if dest == DOCUMENT_ROOT or dest == DB.parent:raise RuntimeError('Backup destination must not be the app data directory')
 dest.mkdir(parents=True,exist_ok=True)
 name='backup_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 target=dest/name;target.mkdir(mode=0o700)
 records=[]
 try:
  dbcopy=target/'database.sqlite3'
  with sqlite3.connect(str(DB)) as source,sqlite3.connect(str(dbcopy)) as sink:source.backup(sink)
  with sqlite3.connect(str(dbcopy)) as c:
   if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('SQLite integrity check failed')
  records.append({'path':'database.sqlite3','bytes':dbcopy.stat().st_size,'sha256':digest(dbcopy)})
  if DOCUMENT_ROOT.exists():
   for src in sorted(DOCUMENT_ROOT.rglob('*')):
    if src.is_symlink():raise RuntimeError('Symlink in documents not allowed: '+str(src))
    if not src.is_file():continue
    relative=src.relative_to(DOCUMENT_ROOT)
    dst=target/'documents'/relative;dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)
    records.append({'path':dst.relative_to(target).as_posix(),'bytes':dst.stat().st_size,'sha256':digest(dst)})
  manifest={'format':'rajan-dental-development-backup-v1','created_at':datetime.now(timezone.utc).isoformat(),'file_count':len(records),'files':records}
  (target/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
  (target/'manifest.json').chmod(0o600)
  verify(target)
 except Exception:
  shutil.rmtree(target)
  raise
 print('CREATED',target)
 return target

def verify(target):
 target=Path(target).resolve()
 manifest=json.loads((target/'manifest.json').read_text(encoding='utf-8'))
 if manifest.get('format')!='rajan-dental-development-backup-v1':raise RuntimeError('Unknown backup format')
 files=manifest['files']
 if len(files)!=manifest['file_count'] or len(files)!=len({f['path'] for f in files}):raise RuntimeError('Invalid manifest')
 actual={p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file() and p.name!='manifest.json'}
 expected={f['path'] for f in files}
 if actual!=expected:raise RuntimeError('Missing or unexpected backup files')
 for record in files:
  p=(target/record['path']).resolve()
  if not p.is_relative_to(target) or not p.is_file():raise RuntimeError('Unsafe or missing path')
  if p.stat().st_size!=record['bytes'] or digest(p)!=record['sha256']:raise RuntimeError('File hash mismatch: '+record['path'])
 with sqlite3.connect(str(target/'database.sqlite3')) as c:
  if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup database damaged')
 print('VERIFIED',target,len(files),'files')
 return True

def restore_test(target):
 """Restore a development backup into a disposable directory, never into live data."""
 verify(target)
 target=Path(target).resolve()
 with tempfile.TemporaryDirectory(prefix='rajan-restore-test-') as temp:
  root=Path(temp)
  shutil.copy2(target/'database.sqlite3',root/'restored.sqlite3')
  if (target/'documents').exists():shutil.copytree(target/'documents',root/'documents')
  with sqlite3.connect(root/'restored.sqlite3') as c:
   if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Restored database integrity failed')
   foreign=c.execute('PRAGMA foreign_key_check').fetchall()
   if foreign:raise RuntimeError(f'Restored database foreign key errors: {len(foreign)}')
   entities=c.execute('SELECT COUNT(*) FROM entities').fetchone()[0]
   patients=c.execute('SELECT COUNT(*) FROM patients').fetchone()[0]
   documents=c.execute('SELECT COUNT(*) FROM patient_documents').fetchone()[0]
   stored=c.execute('SELECT entity_id,stored_name FROM patient_documents').fetchall()
   for eid,name in stored:
    path=root/'documents'/str(eid)/name
    if not path.is_file():raise RuntimeError('Document record has no restored file')
  print('RESTORE TEST PASSED',{'entities':entities,'patients':patients,'documents':documents})
  return True

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['create','verify','restore-test']);parser.add_argument('path');args=parser.parse_args()
 try:
  {'create':create,'verify':verify,'restore-test':restore_test}[args.action](args.path)
 except Exception as ex:
  print('FAILED:',ex,file=sys.stderr);sys.exit(1)
