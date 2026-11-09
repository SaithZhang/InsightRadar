#!/usr/bin/env python3
"""Actual API, sequential user-requested ten-stock acceptance. No mock substitutions."""
import json,time,urllib.request
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'data/acceptance';BASE='http://127.0.0.1:18080/api/v1'
def request(path,body=None):
 data=None if body is None else json.dumps(body).encode()
 req=urllib.request.Request(BASE+path,data=data,headers={} if data is None else {'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
results=[]
for code in ['002463.SZ','600519.SH','688001.SH','300750.SZ','920029.BJ','000001.SZ','600036.SH','300308.SZ','688256.SH','920982.BJ']:
 at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat();run=request('/analyses',{'code':code});rid=run['runId']
 for _ in range(120):
  run=request('/analyses/'+rid)
  if run['status'] not in ['QUEUED','RUNNING']:break
  time.sleep(2)
 (OUT/f'live-{code}.json').write_text(json.dumps(run,ensure_ascii=False,indent=2))
 report=run.get('report') or {};docs=report.get('documents',[])
 result=dict(code=code,at=at,runId=rid,status=run['status'],technicalStatus=report.get('technicalStatus'),eventStatus=report.get('eventStatus'),bars=len(report.get('candles',[])),documents=len(docs),processed=report.get('coverage',{}).get('processedDocuments',0),latestReport=next((d['title'] for d in docs if d.get('latestPeriodicReport')),None),error=run.get('error'),gaps=report.get('dataGaps',[]))
 results.append(result);(OUT/'live-acceptance-summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False),flush=True)
