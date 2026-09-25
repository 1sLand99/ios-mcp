#!/usr/bin/env python3
"""Real screenshot -> both OCR engines -> tap validation on a local, disposable page.

Requires Frida 16 on developer Mac/device only for rotation and temporary idle-timer
control. All recognition/capture/taps use the actual MCP tools. Restores rotation,
rotation-lock and idle timer in finally. Does not alter production OCR.
"""
import argparse
import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from mcp_ocr_engines_test import Client, payload, engine

HTML = '''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<style>body{margin:0;background:white;color:black;font-family:Arial}button{display:block;
font-family:Arial;font-size:23px;height:57px;border:1px solid #bbb;background:white;color:black;
width:96%;margin:4px 2%;padding:0}#status{font-size:10px}</style>
<button id="chinese">中文识别测试</button><button id="english">Hello OCR 12345</button>
<button id="mixed">设置 Wi-Fi 8090</button><div id="status">OCR coordinate fixture</div>
<script>document.querySelectorAll('button').forEach(b=>b.onclick=()=>fetch('/hit',{
method:'POST',body:JSON.stringify({id:b.id,orientation:window.orientation})}));</script>'''

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', required=True)
    p.add_argument('--host-ip', required=True)
    p.add_argument('--frida', default='127.0.0.1:27342')
    p.add_argument('--probe-script', help='Precompiled test-only probe for Frida 17')
    p.add_argument('--scene-rotation', action='store_true', help='Request iOS 16+ foreground app scene rotation')
    p.add_argument('--portrait-only', action='store_true',
                   help='Test the current portrait UI without Frida; landscape is not covered')
    p.add_argument('--port', type=int, default=18715)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    hits = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            data = HTML.encode()
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers(); self.wfile.write(data)
        def do_POST(self):
            hits.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200); self.end_headers()
    server = ThreadingHTTPServer(('0.0.0.0',a.port),Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    c = Client(a.url)
    session = script = None
    if not a.portrait_only:
        import frida
        device = frida.get_device_manager().add_remote_device(a.frida)
        sb = next(p.pid for p in device.enumerate_processes() if p.name == 'SpringBoard')
        source = (Path(a.probe_script) if a.probe_script else
                  Path(__file__).with_name('ocr_orientation_probe.js')).read_text()
        session = device.attach(sb)
        script = session.create_script(source); script.load()
        original = script.exports_sync.state()
    safari_session = None
    old_idle = None
    records = []
    try:
        c.call('press_home'); time.sleep(1); c.call('press_home'); time.sleep(1)
        c.call('open_url', {'url':'http://%s:%d/' % (a.host_ip,a.port)})
        time.sleep(3)
        app = payload(c.call('get_frontmost_app'))
        if script:
            safari_session = device.attach(app['pid'])
            safari_script = safari_session.create_script(source); safari_script.load()
            old_idle = safari_script.exports_sync.idle(True)
            script.exports_sync.lock(False)
        for orientation in ([1] if a.portrait_only else [1,3,4]):
            if script:
                if a.scene_rotation:
                    safari_script.exports_sync.rotate_scene(orientation)
                else:
                    script.exports_sync.rotate(orientation)
            time.sleep(1.5)
            screen = payload(c.call('get_screen_info'))
            image = next(b for b in c.call('screenshot')['result']['content'] if b['type']=='image')
            (out / ('orientation-%d.jpg' % orientation)).write_bytes(base64.b64decode(image['data']))
            if orientation == 1: assert screen['orientation'] == 'portrait', screen
            else: assert 'landscape' in screen['orientation'].lower(), screen
            for selected in ['vision','paddleocr']:
                start = time.monotonic()
                full = engine(c.call('ocr_screen', {'engine':selected,'languages':['zh-Hans','en-US']}),selected)
                for label, expected in [('chinese','中文识别测试'),('english','Hello OCR 12345'),('mixed','8090')]:
                    item = next(t for t in full['texts'] if expected in t['text'])
                    hits.clear()
                    c.call('tap_screen', item['tap']); time.sleep(.25)
                    assert hits and hits[-1]['id'] == label, (selected, orientation, item, hits)
                target = next(t for t in full['texts'] if '8090' in t['text'])
                rect = target['rect']
                roi = {'x':rect['x']-4,'y':rect['y']-4,'width':rect['width']+8,'height':rect['height']+8}
                limited = engine(c.call('ocr_screen', {'engine':selected,'region':roi}),selected)
                match = next(t for t in limited['texts'] if '8090' in t['text'])
                hits.clear(); c.call('tap_screen', match['tap']); time.sleep(.25)
                assert hits and hits[-1]['id'] == 'mixed', (limited, hits)
                records.append({'engine':selected,'orientation':orientation,'screen':screen,
                    'seconds':time.monotonic()-start,'full':full,'roi':roi,'limited':limited,'hits':list(hits)})
                (out/'results.json').write_text(json.dumps(records,indent=2,ensure_ascii=False))
                print('PASS',selected,'orientation',orientation,'Chinese/English/digits, 3 taps + ROI tap',flush=True)
    finally:
        restore = []
        if script:
            if a.scene_rotation and safari_session:
                restore.append(lambda: safari_script.exports_sync.rotate_scene(original['orientation']))
            restore.append(lambda: script.exports_sync.rotate(original['orientation']))
            restore.append(lambda: script.exports_sync.lock(original['locked']))
        if safari_session:
            if old_idle is not None:
                restore.append(lambda: safari_script.exports_sync.idle(old_idle))
            restore.append(safari_session.detach)
        if session:
            restore.append(session.detach)
        restore += [lambda: c.call('press_home'), server.shutdown, server.server_close]
        errors = []
        for action in restore:
            try:
                action()
            except Exception as error:
                errors.append(str(error))
        if errors:
            raise RuntimeError('UI test cleanup failed: ' + '; '.join(errors))

if __name__ == '__main__':
    main()
