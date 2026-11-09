#!/usr/bin/env python3
"""Serial, bounded live spike. Raw outputs remain under ignored data/acceptance."""
import json,subprocess,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
root=Path(__file__).resolve().parents[1];output=root/'data/acceptance';output.mkdir(parents=True,exist_ok=True)
results=[]
for code in ['600519.SH','002463.SZ','688001.SH','300750.SZ','920029.BJ']:
 command=[str(root/'.venv/bin/python'),str(root/'bridge/baostock_bridge.py'),'snapshot','--code',code]
 at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
 try:
  p=subprocess.run(command,capture_output=True,text=True,timeout=180)
  (output/f'gate0-{code}.json').write_text(p.stdout);(output/f'gate0-{code}.log').write_text(p.stderr)
  d=json.loads(p.stdout);r=dict(code=code,at=at,exitCode=p.returncode,error=d.get('error'),rawRows=len(d.get('raw',[])),qfqRows=len(d.get('qfq',[])),calendarRows=len(d.get('calendar',[])),factors=len(d.get('adjustmentEvents',[])),sourceHash=d.get('sourceHash'))
 except subprocess.TimeoutExpired:r=dict(code=code,at=at,error={'code':'PROCESS_TIMEOUT'})
 results.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
(output/'gate0-summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
