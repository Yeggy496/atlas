"""Launch the already-built frontend and backend as one local application."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.request
import webbrowser

root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'backend'))


def open_when_ready(url):
    for _ in range(40):
        try:
            with urllib.request.urlopen(url+'/api/health',timeout=1) as response:
                if response.status==200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(.5)


def main():
    parser=argparse.ArgumentParser(description='Run the ATLAS-Sigma demo locally.')
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if not (root/'frontend'/'dist'/'index.html').exists():
        raise SystemExit('Frontend build missing. Run pnpm build inside frontend.')
    try:
        import uvicorn
        import fastapi
        import ortools
        import sqlalchemy
    except ImportError:
        raise SystemExit('Dependencies missing. Create .venv and install backend/requirements-lock.txt as described in README.md.')
    if args.check:
        print('Production frontend and backend dependencies are ready.')
        return
    url=f'http://127.0.0.1:{args.port}'
    try:
        with urllib.request.urlopen(url+'/api/health',timeout=1) as response:
            health=json.load(response)
        with urllib.request.urlopen(url,timeout=1) as response:
            page=response.read(4096).decode('utf-8')
        if health.get('solver')=='OR-Tools CP-SAT' and 'ATLAS' in page:
            print('ATLAS is already running:',url,flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            return
    except (OSError,ValueError):
        pass
    print('ATLAS-Sigma Demo:',url,flush=True)
    print('Keep this window open. Press Ctrl+C to stop.',flush=True)
    if not args.no_browser:
        threading.Thread(target=open_when_ready,args=(url,),daemon=True).start()
    uvicorn.run('app.main:app',host='127.0.0.1',port=args.port)


if __name__=='__main__':
    main()
