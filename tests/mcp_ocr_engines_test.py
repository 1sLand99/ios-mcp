#!/usr/bin/env python3
"""MCP API regression for both OCR engines. Run on an awake device showing text.
No shell commands or system settings are changed by this script.
"""
import argparse
import concurrent.futures
import json
import time
import urllib.request
from pathlib import Path

class Client:
    def __init__(self, url):
        self.url = url
        self.session = None
        self.next_id = 0
        self.raw('initialize', {'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'ocr-engine-test','version':'1'}})
        self.raw('notifications/initialized', {}, notification=True)

    def raw(self, method, params, notification=False, request_id=None):
        self.next_id += 1
        data = {'jsonrpc':'2.0','method':method,'params':params}
        if not notification: data['id'] = self.next_id if request_id is None else request_id
        headers = {'Content-Type':'application/json','Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-11-25'}
        if self.session: headers['Mcp-Session-Id'] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(data).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=45) as response:
            self.session = response.headers.get('Mcp-Session-Id') or self.session
            text = response.read().decode()
        if not text: return {}
        if text.startswith('event:') or text.startswith('data:'):
            text = next(s[5:].strip() for s in text.splitlines() if s.startswith('data:'))
        return json.loads(text)

    def call(self, name, arguments=None, request_id=None):
        return self.raw('tools/call', {'name':name,'arguments':arguments or {}}, request_id=request_id)

def payload(response):
    assert 'error' not in response, response
    result = response['result']
    assert not result.get('isError'), result
    if 'structuredContent' in result: return result['structuredContent']
    return json.loads(next(c['text'] for c in result['content'] if c['type'] == 'text'))

def engine(response, expected):
    value = payload(response)
    assert value['recognition']['engine'] == expected, value
    if expected == 'paddleocr':
        assert value['recognition']['provider'] == 'CPUExecutionProvider', value
    for item in value['texts']:
        r, p, s = item['rect'], item['tap'], value['screen']
        assert 0 <= p['x'] <= s['width'] and 0 <= p['y'] <= s['height'], item
        assert r['x'] <= p['x'] <= r['x']+r['width'] and r['y'] <= p['y'] <= r['y']+r['height'], item
    return value

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    client = Client(args.url)
    records = []
    def record(name, response, start):
        records.append({'case':name,'seconds':time.monotonic()-start,'response':response})
        print('PASS', name, '%.3fs' % records[-1]['seconds'], flush=True)
    tools = client.raw('tools/list', {})['result']['tools']
    for name in ['ocr_screen','describe_screen']:
        schema = next(t for t in tools if t['name'] == name)['inputSchema']
        assert schema['properties']['engine']['enum'] == ['vision','paddleocr']
        assert schema['properties']['engine']['default'] == 'paddleocr'
        assert 'engine' not in schema.get('required', [])
    # Only one test is active at a time except the explicitly concurrent test below.
    for name, arguments, expected in [
        ('default-cold', {}, 'paddleocr'), ('explicit-vision', {'engine':'vision'}, 'vision'),
        ('default-after-vision', {}, 'paddleocr'),
        ('paddle-warm', {'engine':'paddleocr'}, 'paddleocr'), ('default-after-paddle', {}, 'paddleocr')]:
        start = time.monotonic()
        response = client.call('ocr_screen', arguments)
        value = engine(response, expected)
        assert value['texts'], 'Show a page with visible text before running this test'
        record(name, response, start)
    cold = payload(records[0]['response'])
    warm = payload(records[3]['response'])
    assert cold['recognition']['worker_pid'] == warm['recognition']['worker_pid']
    start = time.monotonic()
    response = client.raw('tools/call', {'name':'ocr_screen'})
    assert engine(response, 'paddleocr')['texts']
    record('omitted-arguments-default-paddle', response, start)
    for invalid in ['other','', 'VISION', None, 1, True, [], {}]:
        for tool in ['ocr_screen','describe_screen']:
            start = time.monotonic()
            response = client.call(tool, {'engine':invalid})
            assert response['error']['code'] == -32602, response
            record(tool + '-invalid-' + repr(invalid), response, start)
    # Reuse a recognized text's fixed-point rect for a real ROI roundtrip.
    target = max(warm['texts'], key=lambda t: t['rect']['width'])
    r = target['rect']
    region = {'x': max(0, r['x']-8), 'y':max(0, r['y']-8), 'width':r['width']+16, 'height':r['height']+16}
    start = time.monotonic()
    response = client.call('ocr_screen', {'engine':'paddleocr','region':region})
    value = engine(response, 'paddleocr')
    assert value['texts'], value
    for item in value['texts']:
        assert region['y'] <= item['tap']['y'] <= region['y']+region['height'], item
    record('paddle-roi', response, start)
    for selected in ['vision','paddleocr']:
        start = time.monotonic()
        response = client.call('ocr_screen', {'engine':selected,'region':{'x':0,'y':100000,'width':30,'height':30}})
        assert engine(response, selected)['texts'] == []
        record(selected + '-empty-roi', response, start)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        def call(selected):
            c = Client(args.url)
            return c.call('ocr_screen', {'engine':selected})
        start = time.monotonic()
        futures = {selected:pool.submit(call, selected) for selected in ['vision','paddleocr']}
        for selected, future in futures.items():
            response = future.result()
            engine(response, selected)
            record('concurrent-' + selected, response, start)
    for selected in ['paddleocr', 'vision']:
        start = time.monotonic()
        response = client.call('describe_screen', {'include_ocr':True,'engine':selected})
        assert payload(response)['ocr_recognition']['engine'] == selected
        record('describe-' + selected, response, start)
    start = time.monotonic()
    response = client.call('describe_screen', {'include_ocr':True})
    assert payload(response)['ocr_recognition']['engine'] == 'paddleocr'
    record('describe-default-paddle', response, start)
    start = time.monotonic()
    response = client.call('describe_screen', {})
    assert 'ocr_recognition' not in payload(response) and 'ocr_texts' not in payload(response)
    record('describe-without-ocr', response, start)
    # Explicit unsupported language fails the selected engine; next default stays Paddle.
    start = time.monotonic()
    response = client.call('ocr_screen', {'engine':'paddleocr','languages':['unsupported-test-language']})
    assert response['result']['isError'], response
    record('paddle-language-error-no-fallback', response, start)
    engine(client.call('ocr_screen', {}), 'paddleocr')
    Path(args.out).write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print('PASS all', len(records), 'MCP engine checks', flush=True)

if __name__ == '__main__':
    main()
