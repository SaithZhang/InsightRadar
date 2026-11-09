#!/usr/bin/env python3
"""Append a fresh retry receipt; preserve the first failed run and acceptance evidence."""
import json,time,urllib.request,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
base='http://127.0.0.1:18080/api/v1'
code=sys.argv[1]
def req(path,data=None):
 r=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={} if data is None else {'Content-Type':'application/json'})
 with urllib.request.urlopen(r,timeout=30) as response:return json.load(response)
id=req('/analyses',{'code':code})['runId']
for _ in range(120):
 d=req('/analyses/'+id)
 if d['status'] not in ['QUEUED','RUNNING']:break
 time.sleep(2)
(root/'data/acceptance'/f'recheck-{code}.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
r=d.get('report') or {};print(json.dumps({'runId':id,'code':code,'status':d['status'],'bars':len(r.get('candles',[])),'documents':len(r.get('documents',[])),'coverage':r.get('coverage'),'error':d.get('error')},ensure_ascii=False))
