#!/usr/bin/env python3
"""Fetch pinned upstream exports/sources; never lower validation or edit ONNX version declarations."""
import hashlib
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.codex-session-data/paddle-build'
LOCK = ROOT / 'third_party/paddleocr/dependencies.lock.json'

def main():
    for item in json.loads(LOCK.read_text())['downloads']:
        path = ROOT / item['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_suffix(path.suffix + '.download')
            subprocess.run(['curl', '-fL', '--retry', '2', '--max-time', '300', item['url'], '-o', str(temporary)], check=True)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != item['sha256']:
                raise RuntimeError('Checksum mismatch: ' + item['url'])
            temporary.rename(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError('Existing file checksum mismatch: ' + str(path))
        print('Verified', path.name)
    for name in ('onnxruntime-1.20.1', 'opencv-4.10.0'):
        if not (WORK / name).exists():
            subprocess.run(['tar', '-xzf', str(WORK / (name + '.tar.gz')), '-C', str(WORK),
                            '--exclude=onnxruntime-1.20.1/onnxruntime/test/testdata'], check=True)
    if not (WORK / 'eigen-e7248b26a1ed53fa030c5c459f7ea095dfd276ac').exists():
        with zipfile.ZipFile(WORK / 'eigen.zip') as archive:
            archive.extractall(WORK)

if __name__ == '__main__':
    main()
