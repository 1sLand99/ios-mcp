# PaddleOCR rootful 兼容性修复与回归（2026-09-25）

本页保留当时的 221 修复记录与包哈希。之后三种正式模式包已重新构建，并在
221/222/223 安装、使用第三方应用回归；最新结果及限制见
[三设备测试报告](PADDLEOCR_THREE_DEVICE_TEST_RESULTS.md)。下表的 222/223 SKIP 是历史状态。
后来还完成了 [iOS 13.5.1 真机补测](PADDLEOCR_IOS13_TEST_RESULTS.md)；本页 iOS 13 SKIP 同样保留为历史记录。

## 问题与修复

设备：192.168.1.221，iPhone SE 第二代 / iPhone12,8 / A13，iOS 14.3，
rootful / Substitute 2.3.1。现有 Vision 可用，Paddle 原先在加载阶段失败：

```text
dyld: Library not loaded: @rpath/libonnxruntime.dylib
Reason: no suitable image found ... code signature invalid
```

worker 返回 SIGABRT（status=6），尚未进入模型推理。文件哈希与安装包相同，
不是模型不支持或推理阶段内存不足的证据。单纯重签、替换 inode、试验性增加
library-validation entitlement 均未解决真实 MCP 调用；这些试验未保留在正式构建中。
尚未确定该越狱环境底层签名策略的全部细节，不把推测当成已定位的内核缺陷。

修复：将相同 ONNX Runtime 1.20.1 CPU 构建生成的官方 combined static framework
归档链接进独立 `mcp-ocr-worker`，不再打包/加载 `libonnxruntime.dylib`。
没有修改设备安全策略、worker entitlement、模型、OCR 算法、请求默认值或 Vision 调用方式。
SpringBoard 主 dylib 仍不链接 ORT/OpenCV，Paddle 仍只用 CPUExecutionProvider。

对照验证通过 A/B/A：原动态 worker 失败 → 静态 worker 冷/热推理成功 →
终止该 worker 并恢复原动态版本后同样失败。随后正常构建并安装完整 rootful deb，
重启 SpringBoard 后再次回归，不只依赖临时替换文件的结果。

## 修改位置

- `scripts/build_paddle_runtime.sh`：iOS 取上游 `static_framework/onnxruntime.framework/onnxruntime`
  作为 `libonnxruntime.a`；macOS 测试工具的动态链接保持不变。
- `mcp-ocr-worker/Makefile`：直接链接 ORT 静态归档，移除 ORT 的动态库和 rpath 参数。
- `Makefile`、`build.sh`：依赖检查改为 `.a`，包内只放 worker 和既有模型/许可证等资源。
- `scripts/check_paddle_binaries.py`、`tests/paddle_package_test.py`：检查静态归档及实际 deb，
  拒绝再次打包 ORT dylib 或把 worker 链接回 ORT dylib。
- 测试脚本：旧 rootful 无 Python 时使用 `ps` 验证待测试 worker PID；UI 测试增加不依赖
  Frida 的 `--portrait-only`，明确不冒充横屏界面测试。

dpkg 升级后确认旧 `/usr/libexec/ios-mcp/libonnxruntime.dylib` 已按包文件归属移除。
没有自定义全盘清理或修改其他应用的文件。

## 221 实际结果

| 验证项 | 结果 | 证据/边界 |
|---|---|---|
| 完整 rootful deb 安装及服务恢复 | PASS | 新 SpringBoard PID，接口 Schema 正常 |
| 旧调用默认 Vision、显式 Vision | PASS | 识别实际屏幕文字 |
| Paddle 冷启动、热调用 | PASS | CPUExecutionProvider，重复调用同一 worker PID |
| Paddle 后省略 engine | PASS | 仍为 Vision |
| 非法 engine | PASS | 8 类值 × 两个工具，共 16 次返回 -32602 |
| `ocr_screen` ROI、两引擎空 ROI | PASS | 实际 ROI 返回框/点击点在范围内；空 ROI 返回空数组 |
| Vision/Paddle 并发 | PASS | 引擎不串用 |
| `describe_screen` 两引擎 | PASS | 正确 OCR 分支 |
| Paddle 不支持的语言 | PASS | 明确错误，不回退；随后默认 Vision 正常 |
| 上述 MCP 接口专项合计 | PASS | 29 项全部通过 |
| 中英数字原生 fixture | PASS | `中文识别测试`、`Hello OCR 12345`、`设置 Wi-Fi 8090` |
| 四个图像方向、已知框中心、ROI | PASS | 真机 native worker，方向 1/3/6/8；不等于物理 UI 旋转 |
| CTC 阈值、空白图、坏图后恢复 | PASS | 原生 worker 实际推理；会话复用 |
| 竖屏页面截图→OCR→tap | PASS | 两引擎各 3 个文字按钮 + 1 次 ROI tap，共 8 次全部命中 |
| 模型缺失、不回退及恢复 | PASS | Paddle 明确 missing；Vision 仍识别出 14 段文字；文件恢复后 Paddle 正常 |
| 队列上限及同时使用 Vision | PASS | 第二个 Paddle 返回 busy；Vision 正常 |
| 取消、不同 session 隔离 | PASS | 其他 session 不误取消；正确取消后 worker 已终止 |
| 超时 | PASS | 30.058 秒返回失败，确认 worker PID 已消失 |
| HTTP 断连 | PASS | 终止相应 worker；后续两引擎恢复 |
| 故障注入资源还原 | PASS | `rec.onnx` 存在，无测试备份残留 |
| 物理横屏 UI 点击 | SKIP | 本轮仅竖屏 UI；四方向覆盖来自原生 fixture |
| iOS 13 真机 | SKIP | **尚未完成 iOS 13 真机验证** |
| 新静态构建在 222/223 的运行 | SKIP | 此前两台通过的是动态运行库构建，不据此声称新构建通过 |
| 全部 MCP 功能、长期压力、Display Zoom | SKIP | 本轮限定 OCR 兼容性和相关路径，不是全量 46 项回归 |

这轮是兼容性回归，不是完整准确率或性能基准。不能把三行固定样本通过解释为通用准确率 100%。

## 构建与二进制检查

- rootful、roothide 正式构建模式（仍为未发布的本地 1.2.6 开发代码）均构建成功。
- worker、ORT 静态归档及两个 OpenCV 静态归档成员均为 arm64、minos=13.0。
- worker 无 ORT 动态库、Vision/CoreML/Metal/Neural Engine 链接；生产入口核验唯一可用
  EP 为 CPUExecutionProvider。SpringBoard 无 ORT/OpenCV 链接。
- 两个实际 deb 的路径、模型/字典 SHA256、许可证、worker minos/架构/链接依赖检查通过。
- 将旧动态 worker 交给新版二进制审计，能按预期拒绝，防止回归检查只会“全部通过”。
- 既有 `-multiply_defined`、arm64e deployment、libzip、旧 helper/libcrypto 等警告仍存在；
  不将此修复等同于对项目所有依赖/功能的 iOS 13 运行认证。
- 未改版本号，未执行 Git 提交、推送或发布。

| 产物 | 字节数 | SHA256 |
|---|---:|---|
| rootful deb | 23683674 | `31cd3b1c49336f4049a33ec474e03202ddea7353df633f2199638b12b6b88089` |
| roothide deb | 23622302 | `0ce532c12a272bc713cd0959264cf5fe267b19c7a03f11dae64a7acf1347021b` |
| ORT iOS 静态归档 | — | `312bd30478c3faead36d477fa6bf338836fb58b76690d586f8fa4fe9dd6c28b9` |

复现：按 [构建文档](PADDLEOCR.md) 生成运行库和所需 deb，安装后运行
`mcp_ocr_engines_test.py`、`paddle_worker_test.py`、`paddle_lifecycle_device_test.py` 和
`ocr_ui_device_test.py --portrait-only`。
本轮原始日志/JSON/截图保存在本地忽略目录 `.codex-session-data/ocr-rootful-fix.ja2uiI/`。
