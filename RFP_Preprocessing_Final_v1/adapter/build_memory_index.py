"""Independent memory index only; no DB, activation, query, or LLM call."""
import argparse,json,sys,os,socket,hashlib
from pathlib import Path
from collections import defaultdict

def build_index(team_src, scope_terms_path=None):
 sys.dont_write_bytecode=True
 root=Path(__file__).resolve().parents[1]
 sys.path.insert(0,str(root));from verify_package import verify
 manifest=verify()
 sys.path.insert(0,str(Path(team_src).resolve()))
 def blocked(*a,**k):raise RuntimeError('network prohibited')
 socket.socket.connect=blocked;socket.create_connection=blocked
 for k in tuple(os.environ):
  if k.endswith('API_KEY') or k.startswith(('LANGFUSE_','BIDMATE_')) or k=='RFP_DATABASE_DSN':os.environ.pop(k)
 from rfp_assistant.retrieval import retrieval,chunking
 from rank_bm25 import BM25Okapi
 assert hashlib.sha256(Path(chunking.__file__).read_bytes()).hexdigest()==manifest['chunker_sha256'],'team chunker SHA differs'
 read=lambda p:[json.loads(l) for l in p.open(encoding='utf-8') if l.strip()]
 chunks=read(root/'final_chunks.jsonl');elements=read(root/'final_elements.jsonl')
 analyzer=retrieval.Analyzer();tokens=[analyzer.tokens(c['payload']) or ['∅'] for c in chunks]
 rows=defaultdict(list)
 for i,c in enumerate(chunks):rows[c['extraction_id']].append(i)
 els={(e['extraction_id'],e['element_id']):e for e in elements}
 sources={e['location']['supplier_metadata']['sha256']:e['extraction_id'] for e in elements}
 scope=json.loads(Path(scope_terms_path).read_text(encoding='utf-8')) if scope_terms_path else {}
 index=retrieval.KeywordIndex('rfp_final_v1_local','includes_unreviewed',chunks,BM25Okapi(tokens),dict(rows),els,scope_terms=scope,source_extraction=sources)
 return index,analyzer

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--team-src',required=True);p.add_argument('--scope-terms');args=p.parse_args()
 index,analyzer=build_index(args.team_src,args.scope_terms)
 print('READY memory-only:',len(index.chunks),'chunks;',len(index.source_extraction),'documents; no search executed')
 print('Index is released when this process exits; import build_index() in an independent test script to keep using it.')
