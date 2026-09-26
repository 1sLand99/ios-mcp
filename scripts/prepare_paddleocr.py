#!/usr/bin/env python3
"""Validate pinned Paddle exports and generate the exact CTC dictionary (developer Mac only)."""
import hashlib
import json
from pathlib import Path
import onnx
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'third_party/paddleocr/models'
EXPECTED = {
    'det.onnx': 'a431985659dc921974177a95adcfbb90fd9e51989a5e04d70d0b75f597b6e61d',
    'det.yml': '98069072e1b6b37d727fd9d9f11725faa46d6ea0de012f2ed26caea011c37699',
    'rec.onnx': 'da72dc72ca4dc220df0dfde68c1dedc31c58d3e76a25871122e5056227d50092',
    'rec.yml': '5dfeb2777f6d0db8177d8128a8acfcf6e6276dc4ac73ea3bf0dc06d6a5e85d8e',
}

def main():
    for name, digest in EXPECTED.items():
        assert hashlib.sha256((MODELS / name).read_bytes()).hexdigest() == digest, name
    # Paddle CTCLabelDecode: blank at zero, configured characters, then an ASCII space.
    characters = yaml.safe_load((MODELS / 'rec.yml').read_text())['PostProcess']['character_dict']
    dictionary = ['', *characters, ' ']
    for name in ('det', 'rec'):
        model = onnx.load(str(MODELS / (name + '.onnx')))
        onnx.checker.check_model(model)
        print(name, 'IR', model.ir_version, 'opset', [(i.domain, i.version) for i in model.opset_import])
        print('inputs', model.graph.input, 'outputs', model.graph.output)
        if name == 'rec':
            assert model.graph.output[0].type.tensor_type.shape.dim[-1].dim_value == len(dictionary)
    (MODELS / 'dictionary.json').write_text(json.dumps(dictionary, ensure_ascii=False) + '\n')
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(MODELS.iterdir()) if p.name != 'sha256.json'}
    (MODELS / 'sha256.json').write_text(json.dumps(hashes, indent=2) + '\n')
    print('CTC classes:', len(dictionary))

if __name__ == '__main__':
    main()
