# 默认 OCR 引擎改为 PaddleOCR（2026-09-26）

## 本次变更

按用户最新要求，省略 `engine` 时由 Vision 改为 **PaddleOCR + ONNX Runtime CPU**。
显式 `engine="vision"` 保留 Apple Vision，显式 `engine="paddleocr"` 保持不变。
选择仍只影响当前请求；不会保存上次引擎、创建偏好设置或在失败时自动换引擎。
非法 engine（包括空字符串、JSON null、错误类型）仍返回参数错误。

- `OCRManager.h/.m`：固定 `defaultEngine` 为 paddleocr，实际执行和旧 native 重载都使用它。
- `MCPServer.m`：两工具 Schema 和描述同步；取消/断连上下文也通过同一默认值解析。
  `describe_screen` 只有确实启用 `include_ocr` 时才创建 OCR 请求上下文，默认仍不做 OCR。
- `README.md`、`README_EN.md`、`docs/PADDLEOCR.md`：同步默认值与显式 Vision 调用方式。
- 测试脚本：默认值断言改为 Paddle，故障隔离中的 Vision 请求改为显式选择；
  生命周期脚本新增 `--omit-engine` 和 `--fault-tool`，可以验证两个工具的默认路径。

这是有意的默认行为变化，不是只改 Schema：原先不传 engine 的调用现在会加载 Paddle
模型，受其并发/资源上限约束；模型缺失时该请求报错，不静默切回 Vision。
Vision 的语言支持、revision、fast/accurate 与 CPU-only accurate 实现均未改动。
模型、运行库、OCR 阈值、坐标映射也未改动；已有窄 ROI 漏检和超长行限制没有因此修复。

## 调用

以下是 `tools/call` 的 params：

```json
{"name":"ocr_screen","arguments":{}}
{"name":"ocr_screen","arguments":{"engine":"paddleocr"}}
{"name":"ocr_screen","arguments":{"engine":"vision","languages":["en-US"]}}
{"name":"describe_screen","arguments":{"include_ocr":true}}
```

第一、二、四种使用 PaddleOCR，第三种使用 Vision。显式 Vision 调用之后再省略 engine，
仍回到 PaddleOCR。`describe_screen` 不启用 `include_ocr` 时依然没有 OCR 层。

## 构建与安装

按 ios-mcp-test 的先构建、安装、实际测试流程执行，限定本次 OCR 改动范围。
本次设备为 `192.168.1.17`，iPhone 7 Plus / iOS 13.5.1 / rootful，使用第三方 Cydia 页面。
构建使用 `printf '1\n1\n' | ./build.sh`，正式模式 `FINALPACKAGE=1 DEBUG=0 STRIP=1`。
通过 MCP 上传并安装，等到新的 SpringBoard PID 和工具 Schema 才开始测试。

本次 rootful 包仍为本地未发布的 1.2.6，23,653,312 字节：
`packages/com.witchan.ios-mcp_1.2.6_iphoneos-arm.deb`。
SHA256：`8c3f61915399d6f523b874b46d456212b451cb4eee54b5f9a5015268a5aa4456`。
实际 deb 的模型/字典/许可证/架构/链接审计通过；worker、ORT/OpenCV 均为 arm64、minos=13.0。
本次仅重打 rootful，未重打 rootless/roothide，也未更新 221/222/223。
未修改版本号、提交、推送或发布。先前同名 rootful 包保存在本轮 `previous-rootful.deb`。

路由单元测试验证实际 production router，识别本身用引擎替身，不冒充真机推理；
包含 nil 默认值、旧 native 方法、显式两引擎、非法参数、默认失败不回退和 200 次并发。
取消上下文单元测试验证 session/typed ID、重复 ID、deadline 和清理；均通过。

## 真机结果

本轮 192.168.1.17 的 84 个检查项最终通过：引擎测试 32 项、iOS 13 兼容性 38 项、
两工具的默认引擎生命周期各 7 项。使用 Cydia 第三方应用，不使用系统应用作为 OCR 样本。

| 功能点 | 状态 | 实际检查 |
| --- | --- | --- |
| `ocr_screen` 省略 engine/arguments | PASS | 实际返回 paddleocr、CPUExecutionProvider，不只检查 Schema |
| 显式 Vision / PaddleOCR | PASS | 各自执行；Vision 后、Paddle 后省略 engine 均返回 Paddle |
| 两引擎并发 | PASS | 引擎不串用；Paddle 忙时显式 Vision 仍有文本结果 |
| 非法 engine / 参数 | PASS | 参数错误，未静默改引擎 |
| `describe_screen(include_ocr=true)` | PASS | 省略 engine 为 Paddle；显式引擎路由正常 |
| `describe_screen` 不启用 OCR | PASS | 没有 OCR 结果层 |
| iOS 13 Vision 语言 / 模式 | PASS | revision 1；默认英文及显式英文正常，显式中文报不支持 |
| 默认 Paddle 中英文与数字 | PASS | fast/accurate 提示均使用固定 mobile 模型，返回对应文字 |
| ROI / 坐标边界 / JPEG | PASS | 两引擎 ROI、非法及超界区域、截图点尺寸检查通过 |
| 两工具默认请求模型缺失 | PASS | 明确 Paddle 错误，无回退；Vision 可用；恢复模型后 Paddle 恢复 |
| 两工具默认请求取消 / session 隔离 | PASS | 正确 session 取消会结束 worker；其他 session 不误取消 |
| 两工具默认请求超时 | PASS | ocr_screen 30.04 秒、describe_screen 30.99 秒返回；确认对应 worker 已退出 |
| 两工具默认请求 HTTP 断连 | PASS | 对应 worker 退出，后续两引擎恢复 |
| 安装与故障注入恢复 | PASS | 主 dylib、worker、两模型及字典的设备 SHA256 与 deb 完全相同，无测试备份残留 |
| 221 / 222 / 223、本轮横屏与点击命中 | SKIP | 本次仅更改默认路由，未重跑这些设备和交互；不能拿此前构建结果冒充本轮结果 |

`describe_screen` 首次故障测试在恢复模型的 SSH 命令上退出 255；已保留失败日志，
重新连通后检查并恢复 `rec.onnx`，随后完整重跑该组 7 项通过。没有将这次基础设施失败
算作首次通过，也没有修改产品逻辑绕过测试。最终模型完整性验证通过。

最终显式 Vision 返回 `engine=vision, revision=1, languages=[en-US]`；随后无 engine 请求
返回 `engine=paddleocr, provider=CPUExecutionProvider, runtime=onnxruntime-1.20.1,
model=PP-OCRv5_mobile, uses_cpu_only=true`。测试结束已返回桌面，SpringBoard PID 为 2973。
这是 iOS 13.5.1 的运行证据，不等同于对 iOS 13.0 或全部应用的识别准确率作保证。

## 复跑

```sh
bash scripts/test_ocr_unit.sh
python3 tests/mcp_ocr_engines_test.py --url http://192.168.1.17:8090/mcp --out engines.json
python3 tests/ocr_ios13_device_test.py --url http://192.168.1.17:8090/mcp --out ios13.json
SSHPASS=YOUR_TEST_DEVICE_PASSWORD python3 tests/paddle_lifecycle_device_test.py \
  --url http://192.168.1.17:8090/mcp --ssh root@192.168.1.17 \
  --resources /usr/share/ios-mcp/paddleocr --app-bundle-id com.saurik.Cydia \
  --omit-engine --fault-tool ocr_screen --out lifecycle-ocr.json
# 再将 --fault-tool 改为 describe_screen，检查其 include_ocr=true 的默认路径。
```

原始日志目录：`.codex-session-data/ocr-default-paddle.jRglzK/`。
此前三设备和 iOS 13.5.1 的报告记录的是 Vision-default 构建，历史数据保留不回写。
