import hashlib,json,sys
from pathlib import Path

def verify():
 root=Path(__file__).resolve().parent
 manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
 required=['final_records.jsonl','final_elements.jsonl','final_chunks.jsonl','structure_mapping.jsonl','preservation_audit.json','regression_results.csv','final_regression_trace.jsonl','README.md','QUICK_START.md','known_limitations.md','handoff_summary.md','verify_package.py']
 errors=[]
 for rel in required:
  if rel not in manifest['files']:errors.append('manifest missing: '+rel)
 for rel,info in manifest['files'].items():
  f=root/rel
  if not f.resolve().is_relative_to(root.resolve()):errors.append('unsafe path: '+rel);continue
  if not f.is_file():errors.append('missing: '+rel);continue
  h=hashlib.sha256()
  with f.open('rb') as stream:
   for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
  if h.hexdigest()!=info['sha256']:errors.append('SHA mismatch: '+rel)
  if f.stat().st_size!=info['bytes']:errors.append('size mismatch: '+rel)
 if errors:raise RuntimeError('\n'.join(errors))
 print('PASS:',len(manifest['files']),'files; SHA-256 and sizes match')
 return manifest
if __name__=='__main__':
 try:verify()
 except Exception as e:print('FAIL:',e,file=sys.stderr);sys.exit(1)
