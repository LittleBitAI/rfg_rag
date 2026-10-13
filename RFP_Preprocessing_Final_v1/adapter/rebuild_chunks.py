import argparse,sys,os,json,socket
from pathlib import Path
from collections import defaultdict
p=argparse.ArgumentParser();p.add_argument('--team-src',required=True);p.add_argument('--token-cache',required=True);p.add_argument('--output',required=True);a=p.parse_args();sys.dont_write_bytecode=True
root=Path(__file__).resolve().parents[1];os.environ['TIKTOKEN_CACHE_DIR']=a.token_cache;sys.path.insert(0,a.team_src)
def blocked(*a,**k):raise RuntimeError('network prohibited')
socket.socket.connect=blocked;socket.create_connection=blocked
from rfp_assistant.retrieval import chunking
import hashlib
m=json.loads((root/'manifest.json').read_text(encoding='utf-8'));assert hashlib.sha256(Path(chunking.__file__).read_bytes()).hexdigest()==m['chunker_sha256']
by=defaultdict(list)
for l in (root/'final_elements.jsonl').read_text(encoding='utf-8').splitlines():
 e=json.loads(l);by[e['extraction_id']].append(e)
chunks=[]
for ex,els in by.items():cs,_=chunking.build_profile(els,ex,'structural');chunks.extend(cs)
text=''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in chunks);assert hashlib.sha256(text.encode()).hexdigest()==m['files']['final_chunks.jsonl']['sha256']
out=Path(a.output);assert not out.exists();out.parent.mkdir(parents=True,exist_ok=True);out.write_text(text,encoding='utf-8');print('PASS',len(chunks))
