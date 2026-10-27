from pathlib import Path
import json,gzip,re,unicodedata,collections,hashlib,urllib.request,urllib.error,datetime
ROOT=Path.home()/'atlas-ingesta'
def nfc(s):return unicodedata.normalize('NFC',s)
def clean(s):return ''.join(c for c in nfc(s) if unicodedata.category(c)!='Cc' or c in '\n\t')
records=[]
with gzip.open(ROOT/'data/chroma-rag_playas_magdalena-20260731-135720.jsonl.gz','rt',encoding='utf-8') as f:
    for line in f:
        r=json.loads(line)
        if '__manifest__' not in r:records.append(r)
# Presupuesto conservador de un experimento que conserva los límites previos
# salvo los cortes nuevos en encabezados jurídicos explícitos. Cap token 1000.
heading=re.compile(r'(?mi)^(?:#{1,6}\s+.*|\s*(?:ART[ÍI]CULO\s+\d|CONSIDERACIONES\b|RESUELVE\b|FALLA\b|ANTECEDENTES\b|DECISI[ÓO]N\b|FUNDAMENTOS\b).*)$')
canonical={clean(r['document']).strip() for r in records}
v2b=[]
for r in records:
    text=clean(r['document']).strip()
    boundaries=sorted({0,len(text)}|{m.start() for m in heading.finditer(text)})
    v2b.extend(text[a:b].strip() for a,b in zip(boundaries,boundaries[1:]) if text[a:b].strip())
new_unique={t for t in v2b if t not in canonical}
result={'snapshot_records':len(records),'unique_documents':len({nfc(r['metadata'].get('source','')) for r in records}),'v2a_exact_reuse':len(records),'v2b_preview_chunks':len(v2b),'v2b_non_exact_unique_chunks':len(new_unique),'baseline_and_selected_judging_calls':900,'question_analysis_calls':40,'answer_generation_calls':80,'dataset_generation_max_calls':40,'document_metadata_max_calls':56,'model_listing_and_probes_max_calls':4,'retry_reserve':40,'enrichment_upper_bound':len(new_unique)}
result['estimated_total']=sum(result[k] for k in ['baseline_and_selected_judging_calls','question_analysis_calls','answer_generation_calls','dataset_generation_max_calls','document_metadata_max_calls','model_listing_and_probes_max_calls','retry_reserve','enrichment_upper_bound'])
result['minimum_minutes_at_4rpm']=round(result['estimated_total']/4,1)
result['warning']='Estimación provisional de cortes sobre v1; no sustituye ejecutar ingesta desde fuentes; reutilización >=98% aún no calculada.'
(Path.home()/'ingesta-budget.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
