#!/bin/bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"
deps=third_party/paddleocr/runtime/macos
out=.codex-session-data/paddle-build
xcrun clang++ -std=c++17 -fobjc-arc -fblocks -O2 -mmacosx-version-min=12.0 \
  -Wno-deprecated-declarations -I"$deps/include" -I"$deps/opencv/include/opencv4" \
  mcp-ocr-worker/main.mm mcp-ocr-worker/PaddleOCR.mm third_party/paddleocr/clipper/clipper.cpp \
  -framework Foundation -framework CoreGraphics -framework ImageIO \
  "$deps/opencv/lib/libopencv_imgproc.a" "$deps/opencv/lib/libopencv_core.a" \
  -L"$deps/lib" -lonnxruntime -lz -Wl,-rpath,"$repo_dir/$deps/lib" -o "$out/mcp-ocr-worker-macos"
