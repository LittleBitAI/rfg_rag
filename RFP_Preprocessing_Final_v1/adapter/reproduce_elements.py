import argparse,json,hashlib
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
 read=lambda p:[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
 for rel in ['adapter/baseline_stage11_elements.jsonl','adapter/patches.jsonl']:
  assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==manifest['files'][rel]['sha256']
 patches={x['element_id']:x for x in read(root/'adapter/patches.jsonl')};out=[];seen=set()
 for e in read(root/'adapter/baseline_stage11_elements.jsonl'):
  if e['element_id'] in patches:
   patch=patches[e['element_id']];assert e==patch['before'];out.extend(patch['after']);seen.add(e['element_id'])
  else:out.append(e)
 assert seen==set(patches);text=''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in out);digest=hashlib.sha256(text.encode()).hexdigest();assert digest==manifest['files']['final_elements.jsonl']['sha256']
 output=Path(a.output);assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True);output.write_text(text,encoding='utf-8');print('PASS',len(out),digest)
if __name__=='__main__':main()
