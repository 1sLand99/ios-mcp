#!/usr/bin/env python3
"""iOS 13 OCR acceptance on a prepared, authorized third-party text page.

No settings, app data or model files are changed. Lifecycle fault injection is
covered separately by paddle_lifecycle_device_test.py.
"""
import argparse
import base64
import io
import json
from pathlib import Path
from PIL import Image
from mcp_ocr_engines_test import Client, engine, payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    client = Client(args.url)
    device = payload(client.call('get_device_info'))
    assert device['systemVersion'].split('.')[0] == '13', device
    records = []

    def record(name, response):
        records.append({'case': name, 'response': response})
        Path(args.out).write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print('PASS', name, flush=True)

    for fast in [True, False]:
        for explicit_languages in [False, True]:
            arguments = {'engine': 'vision', 'fast': fast}
            if explicit_languages:
                arguments['languages'] = ['en-US']
            response = client.call('ocr_screen', arguments)
            value = engine(response, 'vision')
            recognition = value['recognition']
            assert recognition['revision'] == 1 and recognition['languages'] == ['en-US'], recognition
            assert recognition['level'] == ('fast' if fast else 'accurate'), recognition
            assert value['texts'], 'Prepare a page with visible English text'
            record(f'vision-english-fast-{fast}-explicit-languages-{explicit_languages}', response)

    for languages in [['zh-Hans'], ['zh-Hant'], ['zh-Hans', 'en-US']]:
        for fast in [True, False]:
            arguments = {'engine': 'vision', 'languages': languages, 'fast': fast}
            response = client.call('ocr_screen', arguments)
            result = response['result']
            message = ' '.join(c.get('text', '') for c in result['content'])
            assert result.get('isError'), response
            assert 'not supported by Vision revision 1' in message and 'en-US' in message, response
            record(f'vision-chinese-rejected-{languages}-fast-{fast}', response)
            # Omitted engine now selects Paddle, so the same languages must execute there.
            del arguments['engine']
            response = client.call('ocr_screen', arguments)
            assert engine(response, 'paddleocr')['texts']
            record(f'default-paddle-chinese-{languages}-fast-{fast}', response)

    for fast in [True, False]:
        response = client.call('ocr_screen', {'engine': 'paddleocr', 'languages': ['zh-Hans', 'en-US'], 'fast': fast})
        value = engine(response, 'paddleocr')
        assert value['texts'] and value['recognition']['uses_cpu_only'], value
        record(f'paddle-bilingual-cpu-fast-{fast}', response)
    response = client.call('ocr_screen')
    value = engine(response, 'paddleocr')
    assert value['recognition']['languages'] == ['zh-Hans', 'en-US'] and value['recognition']['level'] == 'mobile'
    record('default-after-paddle-still-paddle-bilingual', response)
    engine(client.call('ocr_screen', {'engine':'vision'}), 'vision')
    response = client.call('ocr_screen')
    assert engine(response, 'paddleocr')['texts']
    record('default-after-vision-still-paddle', response)

    invalid_regions = [None, {}, [], {'x': 0, 'y': 0, 'width': 0, 'height': 10},
                       {'x': 0, 'y': 0, 'width': 10, 'height': -1},
                       {'x': True, 'y': 0, 'width': 10, 'height': 10},
                       {'x': 1e308, 'y': 0, 'width': 1e308, 'height': 10}]
    screen = payload(client.call('get_screen_info'))
    for selected in ['vision', 'paddleocr']:
        for region in invalid_regions:
            response = client.call('ocr_screen', {'engine': selected, 'region': region})
            assert response.get('error', {}).get('code') == -32602, response
            record(f'{selected}-invalid-roi-{region}', response)
        region = {'x': -10, 'y': -10, 'width': screen['width'] + 20, 'height': screen['height'] + 20}
        response = client.call('ocr_screen', {'engine': selected, 'region': region})
        assert engine(response, selected)['texts']
        record(f'{selected}-clipped-oversize-roi', response)

    response = client.call('describe_screen', {'include_ocr': True})
    assert payload(response)['ocr_recognition']['engine'] == 'paddleocr'
    record('describe-default-paddle', response)
    image = next(c for c in client.call('screenshot')['result']['content'] if c['type'] == 'image')
    decoded = Image.open(io.BytesIO(base64.b64decode(image['data'])))
    decoded.load()
    assert image['mimeType'] == 'image/jpeg' and decoded.format == 'JPEG'
    assert decoded.size == (screen['width'], screen['height'])
    record('jpeg-fixed-point-dimensions', {'size': decoded.size, 'meta': image.get('_meta'), 'screen': screen})
    print('PASS all', len(records), 'iOS 13 compatibility checks', flush=True)


if __name__ == '__main__':
    main()
