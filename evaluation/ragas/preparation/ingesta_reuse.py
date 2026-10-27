from pathlib import Path
import json,gzip,re,unicodedata,collections,difflib,time
ROOT=Path.home()/'atlas-ingesta'
def clean(s):return ''.join(c for c in unicodedata.normalize('NFC',s) if unicodedata.category(c)!='Cc' or c in '\n\t').strip()
records=[]
with gzip.open(ROOT/'data/chroma-rag_playas_magdalena-20260731-135720.jsonl.gz','rt',encoding='utf-8') as f:
    for line in f:
        r=json.loads(line)
        if '__manifest__' not in r:records.append(r)
by_source=collections.defaultdict(set)
for r in records:by_source[unicodedata.normalize('NFC',r['metadata']['source'])].add(clean(r['document']))
heading=re.compile(r'(?mi)^(?:#{1,6}\s+.*|\s*(?:ART[ÍI]CULO\s+\d|CONSIDERACIONES\b|RESUELVE\b|FALLA\b|ANTECEDENTES\b|DECISI[ÓO]N\b|FUNDAMENTOS\b).*)$')
new=set();exact=0;fuzzy=0;unmatched=[];started=time.monotonic()
for r in records:
    text=clean(r['document']);source=unicodedata.normalize('NFC',r['metadata']['source'])
    bounds=sorted({0,len(text)}|{m.start() for m in heading.finditer(text)})
    for a,b in zip(bounds,bounds[1:]):
        part=text[a:b].strip()
        if not part:continue
        key=(source,part)
        if key in new:continue
        new.add(key)
        if part in by_source[source]:exact+=1;continue
        matched=False
        for candidate in by_source[source]:
            if 2*min(len(part),len(candidate))/(len(part)+len(candidate))<.98:continue
            sm=difflib.SequenceMatcher(None,part,candidate,autojunk=False)
            if sm.quick_ratio()<.98:continue
            if sm.ratio()>=.98:matched=True;break
        if matched:fuzzy+=1
        else:unmatched.append({'source':source,'characters':len(part)})
budget=json.loads((Path.home()/'ingesta-budget.json').read_text())
budget.update(v2b_unique_source_chunks=len(new),v2b_exact_reused=exact,v2b_similar_98_reused=fuzzy,enrichment_after_98=len(unmatched),similarity='difflib.SequenceMatcher, autojunk=False, ratio>=0.98, misma fuente',duration_seconds=round(time.monotonic()-started,2))
budget['estimated_total_after_98']=budget['estimated_total']-budget['enrichment_upper_bound']+len(unmatched)
budget['minimum_minutes_at_4rpm_after_98']=round(budget['estimated_total_after_98']/4,1)
budget['stop_budget']=budget['estimated_total_after_98']>1500
budget['unmatched_by_source']=dict(collections.Counter(x['source'] for x in unmatched))
(Path.home()/'ingesta-budget-final.json').write_text(json.dumps(budget,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in budget.items() if k!='unmatched_by_source'},ensure_ascii=False,indent=2))
