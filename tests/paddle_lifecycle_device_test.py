#!/usr/bin/env python3
"""Explicit fault injection on an authorized test device only.

Stops only the OCR child PID returned by this server, never SpringBoard. Temporarily
renames rec.onnx, restoring it in finally. Requires SSH (SSHPASS) and an awake UI.
"""
import argparse
import concurrent.futures
import http.client
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
from mcp_ocr_engines_test import Client, engine, payload

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', required=True)
    p.add_argument('--ssh', required=True)
    p.add_argument('--resources', required=True)
    p.add_argument('--app-bundle-id', help='Use this third-party app instead of system Settings for visible text')
    p.add_argument('--omit-engine', action='store_true', help='Exercise default Paddle routing and cancellation')
    p.add_argument('--fault-tool', choices=['ocr_screen', 'describe_screen'], default='ocr_screen')
    p.add_argument('--out', required=True)
    a = p.parse_args()
    paddle_arguments = {} if a.omit_engine else {'engine': 'paddleocr'}
    fault_arguments = dict(paddle_arguments)
    if a.fault_tool == 'describe_screen':
        fault_arguments['include_ocr'] = True
    assert os.environ.get('SSHPASS'), 'Set SSHPASS for the test device'
    c = Client(a.url)
    def show_text():
        c.call('press_home')
        time.sleep(1)
        c.call('press_home')
        time.sleep(1)
        if a.app_bundle_id:
            c.call('launch_app', {'bundle_id':a.app_bundle_id})
        else:
            c.call('open_url', {'url':'App-Prefs:'})
        time.sleep(1)
    show_text()
    records = []
    def ssh(command, check=True):
        return subprocess.run(['sshpass','-e','ssh','-o','PreferredAuthentications=password',
            '-o','PubkeyAuthentication=no','-o','ConnectTimeout=5',a.ssh,command],
            text=True, capture_output=True, timeout=10, check=check)
    def record(name, value):
        records.append({'case':name,'result':value})
        print('PASS', name, flush=True)
        Path(a.out).write_text(json.dumps(records, indent=2, ensure_ascii=False))
    def paddle():
        return engine(c.call('ocr_screen', paddle_arguments), 'paddleocr')
    def process_path(pid):
        # procps is not installed on every jailbreak; use libproc only for diagnostics.
        code = ('import ctypes; b=ctypes.create_string_buffer(4096); '
                'ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(%d,b,4096); '
                'print(b.value.decode())') % pid
        # Older rootful test devices may have ps but no Python. This is only
        # diagnostic PID ownership verification, not an OCR runtime dependency.
        result = ssh('if command -v python3 >/dev/null 2>&1; then python3 -c ' +
                     shlex.quote(code) + '; else ps -p %d -o command=; fi' % pid,
                     check=False)
        # ps returns 1 for an absent PID. A broken SSH/diagnostic command must
        # not be mistaken for proof that the worker exited.
        if result.returncode not in (0, 1) or result.stderr.strip():
            raise RuntimeError('Cannot verify worker PID: ' + result.stderr)
        return result.stdout.strip()
    def stop(pid):
        command = process_path(pid)
        assert 'mcp-ocr-worker' in command, command
        ssh('kill -STOP %d' % pid)
    def gone(pid):
        path = process_path(pid)
        assert 'mcp-ocr-worker' not in path, path
    def failure(result):
        if a.fault_tool == 'describe_screen':
            text = payload(result).get('ocr_error')
            assert isinstance(text, str), result
        else:
            assert result['result']['isError'], result
            text = result['result']['content'][0]['text']
        assert 'paddleocr' in text.lower(), text
        return text
    # Missing resource even after a warm inference must not be hidden by session reuse.
    paddle()
    model = a.resources.rstrip('/') + '/rec.onnx'
    backup = model + '.mcp-test-backup'
    ssh('test -f {0} && test ! -e {1} && mv {0} {1}'.format(shlex.quote(model), shlex.quote(backup)))
    try:
        error = failure(c.call(a.fault_tool, fault_arguments))
        assert 'missing' in error, error
        vision = engine(c.call('ocr_screen', {'engine':'vision'}), 'vision')
        assert vision['count'] > 0, 'Vision must still recognize visible text'
        record('missing-model-no-fallback-vision-survives', {'error':error,'vision_count':vision['count']})
    finally:
        ssh('mv {0} {1}'.format(shlex.quote(backup), shlex.quote(model)))
    paddle()
    record('model-restored-recovery', True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        for kind in ['cancel', 'timeout']:
            pid = paddle()['recognition']['worker_pid']
            stop(pid)
            start = time.monotonic()
            try:
                future = pool.submit(c.call, a.fault_tool, fault_arguments, 'fault-' + kind)
                time.sleep(.5)
                if kind == 'cancel':
                    busy = failure(Client(a.url).call(a.fault_tool, fault_arguments))
                    assert 'busy' in busy, busy
                    vision = engine(Client(a.url).call('ocr_screen', {'engine':'vision'}), 'vision')
                    assert vision['count'] > 0
                    record('bounded-queue-and-concurrent-vision', {'error':busy,'vision_count':vision['count']})
                    # A different session's cancellation must not cancel this request.
                    other = Client(a.url)
                    # Existing server initializes clients with one shared session token.
                    # Explicitly vary the header to test the cancellation registry's key,
                    # not merely the number of Client objects in this test process.
                    other.session = c.session + '-different-session'
                    other.raw('notifications/cancelled', {'requestId':'fault-cancel'}, notification=True)
                    time.sleep(.2)
                    assert not future.done(), 'cancellation leaked across sessions'
                    c.raw('notifications/cancelled', {'requestId':'fault-cancel'}, notification=True)
                result = future.result(timeout=38)
                error = failure(result)
                duration = time.monotonic() - start
                if kind == 'timeout': assert 29 <= duration <= 35, duration
                gone(pid)
                record(kind + '-terminates-worker', {'seconds':duration,'error':error,'pid':pid})
            finally:
                # A failed test must not leave its child suspended.
                ssh('kill -CONT %d' % pid, check=False)
            assert paddle()['recognition']['worker_pid'] != pid
            show_text()
            engine(c.call('ocr_screen', {'engine':'vision'}), 'vision')
    # A client that abandons its HTTP connection also terminates the exact worker.
    pid = paddle()['recognition']['worker_pid']
    stop(pid)
    u = urlsplit(a.url)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
    try:
        conn.request('POST', u.path, json.dumps({'jsonrpc':'2.0','id':'disconnect', 'method':'tools/call',
            'params':{'name':a.fault_tool,'arguments':fault_arguments}}),
            {'Content-Type':'application/json','Mcp-Session-Id':c.session,'MCP-Protocol-Version':'2025-11-25'})
        time.sleep(.5)
        conn.close()
        time.sleep(.5)
        gone(pid)
        record('disconnect-terminates-worker', {'pid':pid})
    finally:
        conn.close()
        ssh('kill -CONT %d' % pid, check=False)
    paddle()
    engine(c.call('ocr_screen', {'engine':'vision'}), 'vision')
    record('post-fault-both-engines-recover', True)

if __name__ == '__main__':
    main()
