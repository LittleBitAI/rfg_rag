import json,hashlib
from pathlib import Path
p=Path(__file__).resolve().parents[1];m=json.loads((p/'manifest.json').read_text(encoding='utf-8'))
for rel,v in m['files'].items():
 f=p/rel;assert f.is_file(),rel;assert hashlib.sha256(f.read_bytes()).hexdigest()==v['sha256'],rel
print('PASS',len(m['files']),'files')
