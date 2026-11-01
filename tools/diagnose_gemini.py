"""Opt-in Gemini diagnostic: one model metadata GET and one minimal inference POST.
Does not print the key, request headers or raw provider error bodies.
"""
import json
from pathlib import Path
import sys
import time
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
import os
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--low-thinking',action='store_true')
parser.add_argument('--skip-metadata',action='store_true')
args=parser.parse_args()
app.load_env()
key=os.getenv('GEMINI_API_KEY')
model=os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite')
if not key:
    raise SystemExit('No Gemini key configured.')
if not app.re.fullmatch(r'[a-zA-Z0-9._-]+',model):
    raise SystemExit('Invalid model identifier.')
print('Configured model:',model,flush=True)
base=f'https://generativelanguage.googleapis.com/v1beta/models/{model}'
checks=[('Model availability',base,None),('Minimal prompt',base+':generateContent',{'contents':[{'parts':[{'text':'Reply with OK.'}]}],'generationConfig':({**app.generation_config(model),'maxOutputTokens':128} if args.low_thinking else {'maxOutputTokens':32})})]
if args.skip_metadata:
    checks=checks[1:]
for label,url,body in checks:
    started=time.monotonic()
    request=Request(url,data=json.dumps(body).encode() if body else None,headers={'x-goog-api-key':key,'Content-Type':'application/json'})
    try:
        with urlopen(request,timeout=30,context=app.tls_context()) as response:
            data=json.load(response)
            if body is None:
                print(label,': HTTP',response.status,'methods=',data.get('supportedGenerationMethods',[]),flush=True)
            else:
                print(label,': HTTP',response.status,'candidates=',len(data.get('candidates',[])),'usage=',data.get('usageMetadata',{}),flush=True)
    except HTTPError as exc:
        print(label,': HTTP',exc.code,flush=True)
    except (URLError,OSError) as exc:
        reason=exc.reason if isinstance(exc,URLError) else exc
        print(label,': connection failure type=',type(reason).__name__,flush=True)
    print('Elapsed:',round(time.monotonic()-started,2),'seconds',flush=True)
