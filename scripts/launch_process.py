#!/usr/bin/env python3
import os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];service=sys.argv[1]
commands={'server':[str(Path(os.environ['JAVA_HOME'])/'bin/java'),'-jar','target/insightradar-0.2.0.jar'],'web':['node','node_modules/vite/bin/vite.js','preview','--host','127.0.0.1','--port','15173','--strictPort']}
with (root/'data/logs'/f'{service}.log').open('ab') as log:
 proc=subprocess.Popen(commands[service],cwd=root/('server' if service=='server' else 'web'),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(root/'data/run'/f'{service}.pid').write_text(str(proc.pid)+'\n')
