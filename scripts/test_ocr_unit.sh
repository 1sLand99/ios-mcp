#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
out=.codex-session-data/paddle-build/tests
mkdir -p "$out"
xcrun clang -fobjc-arc -fblocks -Wno-incomplete-implementation -framework Foundation \
  OCRManager.m tests/ocr_router_tests.m -o "$out/ocr-router-tests"
"$out/ocr-router-tests"
xcrun clang -fobjc-arc -fblocks -framework Foundation \
  MCPOCRRequestContext.m tests/ocr_context_tests.m -o "$out/ocr-context-tests"
"$out/ocr-context-tests"
