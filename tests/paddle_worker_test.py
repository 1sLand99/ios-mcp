#!/usr/bin/env python3
"""Real native CPU inference with fixed fixtures, all 4 orientations, ROI and resource errors.

python tests/paddle_worker_test.py --worker .codex-session-data/paddle-build/mcp-ocr-worker-macos
The --worker command can also be an SSH command running the installed iOS worker.
"""
import argparse
import base64
import io
import json
import select
import shlex
import shutil
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]

def fixture():
    image = Image.new('RGB', (900, 520), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc', 48)
    for y, text in [(70, '中文识别测试'), (220, 'Hello OCR 12345'), (370, '设置 Wi-Fi 8090')]:
        draw.text((60, y), text, font=font, fill='black')
    return image

def payload(image, orientation=1, roi=(0, 0, 1, 1), confidence=.3):
    stream = io.BytesIO()
    image.save(stream, 'PNG')
    return {'image': base64.b64encode(stream.getvalue()).decode(), 'orientation': orientation,
            'roi': roi, 'min_confidence': confidence}

class Worker:
    def __init__(self, command, resources):
        self.p = subprocess.Popen([*shlex.split(command), '--resources', resources], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def call(self, request):
        data = json.dumps(request).encode()
        self.p.stdin.write(struct.pack('!I', len(data)) + data)
        self.p.stdin.flush()
        def read(n):
            out = bytearray()
            deadline = time.monotonic() + 40
            while len(out) < n:
                assert select.select([self.p.stdout], [], [], max(0, deadline - time.monotonic()))[0], 'worker timeout'
                chunk = self.p.stdout.read1(n - len(out))
                assert chunk, 'worker exited: ' + str(self.p.poll())
                out.extend(chunk)
            return bytes(out)
        size, = struct.unpack('!I', read(4))
        assert size <= 1024 * 1024
        return json.loads(read(size))

    def close(self):
        self.p.stdin.close()
        try:
            self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait()

def validate(result, expected):
    assert 'error' not in result, result
    assert result['provider'] == 'CPUExecutionProvider', result
    joined = '\n'.join(t['text'] for t in result['texts'])
    for text in expected:
        assert text in joined, (text, joined)
    for item in result['texts']:
        x, y, w, h = item['box']
        assert 0 <= x <= 1 and 0 <= y <= 1 and w > 0 and h > 0 and x+w <= 1.001 and y+h <= 1.001, item
    return joined

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', required=True)
    parser.add_argument('--resources', default=str(ROOT / 'third_party/paddleocr/models'))
    parser.add_argument('--skip-resource-tests', action='store_true')
    parser.add_argument('--out', help='Separate result file for each platform/device')
    args = parser.parse_args()
    image = fixture()
    artifacts = ROOT / '.codex-session-data/paddle-build/tests'
    artifacts.mkdir(exist_ok=True)
    image.save(artifacts / 'fixture.png')
    worker = Worker(args.worker, args.resources)
    records = []
    try:
        pid = None
        for orientation, rotation in [(1, 0), (3, 180), (6, 90), (8, 270)]:
            start = time.monotonic()
            result = worker.call(payload(image.rotate(rotation, expand=True), orientation))
            print('orientation', orientation, validate(result, ['中文识别测试', 'Hello OCR 12345', '8090']))
            if pid is not None: assert result['worker_pid'] == pid, 'sessions not reused'
            pid = result['worker_pid']
            # Match known drawn line centers, testing resize + orientation coordinate mapping.
            for text, y in [('中文识别测试', .2), ('Hello OCR 12345', .49), ('8090', .78)]:
                item = next(t for t in result['texts'] if text in t['text'])
                assert abs(item['box'][1] + item['box'][3]/2 - y) < .06, item
            records.append({'case': 'orientation-' + str(orientation), 'seconds': time.monotonic()-start, 'result': result})
        result = worker.call(payload(image, roi=(0, .35, 1, .3)))
        assert '中文' not in validate(result, ['Hello OCR 12345'])
        for t in result['texts']:
            assert t['box'][1] >= .349 and t['box'][1] + t['box'][3] <= .651, t
        records.append({'case': 'roi', 'result': result})
        unfiltered = worker.call(payload(image, confidence=0))
        strict = worker.call(payload(image, confidence=.99))
        expected = [t['text'] for t in unfiltered['texts'] if t['confidence'] >= .99]
        assert [t['text'] for t in strict['texts']] == expected
        assert len(strict['texts']) < len(unfiltered['texts']), 'Fixture should exercise threshold filtering'
        records.append({'case':'ctc-threshold-0.99','result':strict,'unfiltered':unfiltered})
        blank = worker.call(payload(Image.new('RGB', (900, 520), 'white')))
        assert blank['texts'] == [], blank
        malformed = worker.call({'image': 'invalid', 'orientation': 1, 'roi': [0,0,1,1]})
        assert 'PaddleOCR' in malformed['error'], malformed
        validate(worker.call(payload(image)), ['Hello OCR 12345'])
        print('PASS orientations / coordinates / ROI / CTC threshold / blank / reuse / malformed image recovery')
    finally:
        worker.close()
    if not args.skip_resource_tests:
        with tempfile.TemporaryDirectory(prefix='paddle-resource-test-') as tmp:
            path = Path(tmp) / 'models'
            shutil.copytree(args.resources, path)
            worker = Worker(args.worker, str(path))
            try:
                validate(worker.call(payload(image)), ['12345'])
                with (path / 'rec.onnx').open('r+b') as f:
                    f.write(b'BROKEN')
                result = worker.call(payload(image))
                assert 'checksum mismatch' in result['error'], result
                (path / 'det.onnx').unlink()
                result = worker.call(payload(image))
                assert 'missing' in result['error'], result
                print('PASS warm-session corrupt/missing models: explicit failure, no fallback')
            finally:
                worker.close()
    destination = Path(args.out) if args.out else artifacts / 'worker-results.json'
    destination.write_text(json.dumps(records, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
