export TARGET = iphone:clang:latest:13.0
# A separate arm64 executable runs on both arm64 and arm64e devices. No arm64e ABI mixing.
export ARCHS = arm64
export DEBUG = 0
include $(THEOS)/makefiles/common.mk
TOOL_NAME = mcp-ocr-worker
PADDLE_DEPS = ../third_party/paddleocr/runtime/ios
mcp-ocr-worker_FILES = main.mm PaddleOCR.mm ../third_party/paddleocr/clipper/clipper.cpp
mcp-ocr-worker_CFLAGS = -fobjc-arc -Wno-deprecated-declarations -I$(PADDLE_DEPS)/include -I$(PADDLE_DEPS)/opencv/include/opencv4
mcp-ocr-worker_CCFLAGS = -std=c++17 -fexceptions -fcxx-exceptions
mcp-ocr-worker_FRAMEWORKS = Foundation CoreGraphics ImageIO
mcp-ocr-worker_LIBRARIES = z
# Use ORT's combined static framework archive. A separately signed ORT dylib can
# be rejected by older rootful dyld/AMFI when spawned from SpringBoard (iOS 14).
# The runtime still lives only in this isolated worker, never in SpringBoard.
mcp-ocr-worker_LDFLAGS = $(PADDLE_DEPS)/lib/libonnxruntime.a $(PADDLE_DEPS)/opencv/lib/libopencv_imgproc.a $(PADDLE_DEPS)/opencv/lib/libopencv_core.a
mcp-ocr-worker_CODESIGN_FLAGS = -Sentitlements.plist
mcp-ocr-worker_INSTALL_PATH = /usr/libexec/ios-mcp
include $(THEOS_MAKE_PATH)/tool.mk
