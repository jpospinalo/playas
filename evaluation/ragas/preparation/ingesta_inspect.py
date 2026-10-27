"""Inspección exclusivamente de lectura sobre v1 y documentos locales."""
from pathlib import Path
import json,urllib.request,subprocess,unicodedata,hashlib,gzip,collections
ROOT=Path.home()/'atlas-ingesta'
def request(url,body=None):
    data=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
base='http://184.197.221.114:8000/api/v2/tenants/default_tenant/databases/default_database/collections'
collections_info=request(base)
result={'collections':[{'name':x['name'],'id':x['id']} for x in collections_info]}
v1=next(c for c in collections_info if c['name']=='rag_playas')
result['v1_count']=request(base+'/'+v1['id']+'/count')
sample=request(base+'/'+v1['id']+'/get',{'limit':1,'include':['embeddings','metadatas','documents']})
result['v1_dimension']=len(sample['embeddings'][0]);result['v1_metadata_keys']=sorted(sample['metadatas'][0]);result['v1_document_sample']=sample['documents'][0][:220]
assert result['v1_count']==5888 and result['v1_dimension']==768
result['ollama_models']=[{'name':m['name'],'digest':m['digest']} for m in request('http://3.217.204.19:11434/api/tags')['models']]
sources=[]
target=ROOT/'evaluation/ragas/sources';target.mkdir(parents=True,exist_ok=True)
for p in sorted((ROOT/'data/documents/raw').rglob('*')):
    if p.suffix.lower() not in ['.md','.pdf']:continue
    if p.suffix.lower()=='.pdf':
        proc=subprocess.run(['pdftotext','-layout',str(p),'-'],capture_output=True)
        if proc.returncode:continue
        text=proc.stdout.decode('utf-8','replace')
    else:text=p.read_text(encoding='utf-8-sig')
    text=unicodedata.normalize('NFC',text)
    key=hashlib.sha256(p.relative_to(ROOT/'data/documents/raw').as_posix().encode()).hexdigest()[:16]
    (target/(key+'.txt')).write_text(text,encoding='utf-8')
    sources.append({'source_id':key,'path':p.relative_to(ROOT).as_posix(),'type':p.parent.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'characters':len(text),'pages':text.count('\f') if p.suffix=='.pdf' else None})
(target/'manifest.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2),encoding='utf-8')
result['source_documents']=len(sources);result['source_types']=dict(collections.Counter(s['type'] for s in sources));result['source_characters']=sum(s['characters'] for s in sources)
result['sources_empty_or_small']=[s['source_id'] for s in sources if s['characters']<200]
gold=list((ROOT/'data/documents/gold').rglob('*.jsonl'))
result['gold_files']=len(gold)
result['snapshot_record_shape']={}
with gzip.open(ROOT/'data/chroma-rag_playas_magdalena-20260731-135720.jsonl.gz','rt',encoding='utf-8') as f:
    for line in f:
        r=json.loads(line)
        if '__manifest__' in r:continue
        result['snapshot_record_shape']={'keys':list(r),'metadata_keys':list(r.get('metadata',{})),'document_head':r.get('document','')[:220]};break
(Path.home()/'ingesta-inspect.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
