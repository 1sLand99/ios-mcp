#!/usr/bin/env python3
"""Inspect actual Mach-O load commands, architectures, imports and linked frameworks."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def output(*args):
    return subprocess.check_output(args, text=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', default='mcp-ocr-worker/.theos/obj/mcp-ocr-worker')
    parser.add_argument('--out', default='.codex-session-data/paddle-build/binary-audit.json')
    args = parser.parse_args()
    paths = [ROOT / args.worker, ROOT / 'third_party/paddleocr/runtime/ios/lib/libonnxruntime.a']
    paths += sorted((ROOT / 'third_party/paddleocr/runtime/ios/opencv/lib').glob('*.a'))
    assert len(paths) == 4, paths
    report = []
    for path in paths:
        architectures = output('lipo', '-archs', str(path)).strip()
        assert architectures == 'arm64', (path, architectures)
        commands = output('otool', '-l', str(path))
        minimums = re.findall(r'\bminos\s+(\S+)', commands)
        minimums += re.findall(r'LC_VERSION_MIN_IPHONEOS\s+cmdsize \d+\s+version (\S+)', commands)
        assert minimums, 'no OS version commands: ' + str(path)
        assert all(tuple(map(int, v.split('.'))) <= (13, 0, 0) for v in minimums), set(minimums)
        platforms = set(re.findall(r'\bplatform\s+(\S+)', commands))
        assert platforms <= {'2', 'IOS'}, platforms
        links = output('otool', '-L', str(path)) if path.suffix != '.a' else ''
        assert 'onnxruntime' not in '\n'.join(links.splitlines()[1:]), 'ORT must be statically linked into the worker: ' + links
        assert not re.search(r'CoreML|Metal|Vision|Neural|onnxruntime_providers', links), links
        imports = output('nm', '-u', str(path))
        assert not re.search(r'VNRecognize|MLModel|MTLCreate|_ANE', imports), 'accelerator/Vision symbols'
        report.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'arch': architectures, 'minimum_versions': sorted(set(minimums)), 'links': links,
                       'undefined_symbols': imports})
        print('PASS', path.name, 'arm64', sorted(set(minimums)), 'no accelerator/Vision links')
    target = ROOT / args.out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
