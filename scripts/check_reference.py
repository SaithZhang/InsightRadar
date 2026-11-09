#!/usr/bin/env python3
"""Independent Decimal oracle. Test-only calculations, never used by runtime APIs."""
import json
from decimal import Decimal,localcontext
from pathlib import Path
root=Path(__file__).resolve().parents[1]
d=json.loads((root/'server/target/technical-vector.json').read_text())
bars=d['bars'];close=[Decimal(b['close']) for b in bars]
with localcontext() as ctx:
 ctx.prec=50
 ma=lambda n,end:sum(close[end-n+1:end+1])/n
 true_ranges=[max(Decimal(b['high'])-Decimal(b['low']),abs(Decimal(b['high'])-close[i-1]),abs(Decimal(b['low'])-close[i-1])) for i,b in enumerate(bars) if i]
 atr=sum(true_ranges[:14])/14
 for tr in true_ranges[14:]: atr=(13*atr+tr)/14
 expected={'ma20':ma(20,119),'ma55':ma(55,119),'ma20FiveBarsAgo':ma(20,114),'ma55FiveBarsAgo':ma(55,114),'atr14':atr}
 for name,value in expected.items():
  actual=Decimal(d['result']['indicators'][name]);assert abs(actual-value)<Decimal('1e-28'),(name,actual,value)
 print('PASS: 5 indicators independently reconciled (50-digit oracle; tolerance 1e-28)')
