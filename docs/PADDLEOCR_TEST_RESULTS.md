# OCR 双引擎开发测试记录（2026-09-25，未发版）

本页保留最初 222 动态运行库构建的测试数据及包哈希，不代表之后所有构建。
后续 221（iOS 14.3 / rootful）的静态链接修复与回归见
[兼容性补测记录](PADDLEOCR_ROOTFUL_COMPATIBILITY.md)。223 也已用之前的动态运行库
构建完成专项补测。随后三台设备均已安装新构建的静态链接正式模式包，并完成
第三方应用 OCR 专项测试；最新覆盖、识别误差与边界限制见
[三设备测试报告](PADDLEOCR_THREE_DEVICE_TEST_RESULTS.md)。
之后又完成了 [iOS 13.5.1 真机补测](PADDLEOCR_IOS13_TEST_RESULTS.md)，本页原始 iOS 13 未验证状态不代表最新进展。

## 结论与边界

实现了请求级 `engine` 选择、Vision 保留、PaddleOCR 原生 CPU worker、打包和可执行测试。
未改版本号，仍为 1.2.6；没有执行 git add/commit/push、创建分支、tag 或发布。
新增依赖按 iOS 13.0 构建，不等于已完成 iOS 13 运行验收。

**尚未完成 iOS 13 真机验证**。本页最初测试时 221 不在线，223 尚未安装当时的包；
后续验证范围见上方补测记录。缺少 iOS 13 设备的四项重点验收
（默认 Vision 英文、显式 Vision 英文、Vision 中文明确报错、Paddle 中英数字）
全部标记 SKIP，不把较新设备或宿主机结果冒充旧系统结果。

实际安装并测试：192.168.1.222，iPhone 7 / iPhone9,3 / A10 / iOS 15.8.8，
roothide，375×667 固定屏幕点，750×1334 截图像素。模型不需要联网推理。

## 依赖与兼容性证据

- ONNX Runtime 1.20.1，从锁定源码构建，CPUExecutionProvider 唯一提供者。
  [官方该版本 iPhone 构建配置](https://github.com/microsoft/onnxruntime/blob/v1.20.1/tools/ci_build/github/apple/default_full_ios_framework_build_settings.json)
  使用 iOS 13.0；本项目明确关闭 CoreML/XNNPACK，不沿用 iOS 15 的预编译包。
- PP-OCRv5_mobile 官方 PaddlePaddle ONNX 导出，检测模型 IR 6/opset 11、
  识别模型 IR 3/opset 7、float32、CTC 18,385 类；没有改写模型声明。
  通过 ONNX checker，以及 Mac 和真机的实际模型加载/原生推理。
- OpenCV 4.10.0 core/imgproc、Clipper 6.4.2、锁定 Eigen 提交。
  完整下载 URL、revision、SHA256 与许可证见 `third_party/paddleocr/`。
- 实际 Mach-O 检查：worker 和 ORT 均 arm64、minos=13.0；
  两个 OpenCV 静态库的成员也为 iOS 13.0。全量 undefined symbols 已留档。
  ORT 的 filesystem 依赖在 [Apple 的支持表](https://developer.apple.com/xcode/cpp/)中最低为 iOS 13.0。
  未使用真实 iOS 13 dyld cache 做完整符号解析，仍需旧系统真机验收。
- worker/ORT 无 Vision、CoreML、Metal、Neural Engine 动态链接；
  worker 初始化时硬性检查可用 EP 只有 CPU。SpringBoard 主 dylib 不链接 ORT/OpenCV。
  `recognition.provider` 和日志同时确认实际分支。
- 三个 deb 都解包核对了目录前缀、模型/字典 SHA256、许可证、
  worker/runtime 的架构/minos/链接依赖，不只检查 staging 目录。
- 原有非 OCR 的 `mcp-ldid` 仍静态链接带 iOS 15 对象版本的 libcrypto，
  rootful 构建会提示版本不匹配；既有 arm64e/旧链接参数/libzip 警告也仍存在。
  新 OCR 不链接该 helper/libcrypto，但不能因此声称整个安装包所有旧功能已在 iOS 13 验证。

## 功能与隔离验收

| 测试 | 结果 | 实际观察 |
|---|---|---|
| 旧调用省略 engine | PASS | Vision；原参数/结果坐标保留 |
| 显式 vision | PASS | Vision |
| 显式 paddleocr | PASS | 原生 ORT CPU，中英数字识别；非 Vision 代理 |
| Paddle 后省略 engine | PASS | 回到 Vision，无全局偏好 |
| 两引擎实际并发 | PASS | 各自返回正确引擎，无串用 |
| 两个 Paddle 并发 | PASS | 一条执行，另一条明确 busy，不排队积压 |
| 非法 engine | PASS | 两个工具均对 8 类非法值返回 -32602 |
| describe_screen | PASS | 两引擎 OCR 层；保持原部分结果/ocr_error 约定 |
| 真机模型缺失 | PASS | Paddle 明确 missing；同时 Vision 仍识别出 23 段文字；恢复资源后恢复 |
| 损坏模型/非法图像 | PASS（Mac 原生 worker） | 明确校验失败/解析失败，不回退；后续有效请求恢复 |
| 会话复用 | PASS | 连续请求 worker PID 不变 |
| 请求取消 | PASS | 只终止对应 worker，确认 PID 不再存在，随后两引擎正常 |
| 30 秒超时 | PASS | 人为暂停确切 worker 后约 30.04 秒返回错误，worker 被杀并回收 |
| HTTP 断连 | PASS | 终止 worker，后续重新初始化成功 |
| 默认/并发路由单元测试 | PASS | 生产 router + 引擎替身，200 并发调用；不冒充真实推理 |
| 取消上下文单元测试 | PASS | session、字符串/数字 ID、重复 ID、断连、deadline、清理 |
| 中英数字/方向/ROI 真机 UI | PASS | 竖屏、左横屏、右横屏；两引擎各 3 次全屏 tap + 1 次 ROI tap，共 24 次全部命中 |
| 四方向原生 fixture | PASS | 1/3/6/8 图像方向，含倒置图像；准确文字与已知框中心校验 |
| CTC 置信度阈值 | PASS（Mac + 真机原生 worker） | 0 与 0.99 的过滤按未舍入的平均 CTC 概率验证；不与 Vision 置信度直接等价 |
| 长时间压力、极端 jetsam、Display Zoom | SKIP | 未做长期压力/系统配置变更，不声明覆盖 |
| iOS 13/14/18 本次包运行 | SKIP | 只有上述 iOS 15.8.8 真机计入通过 |

UI 测试由本机提供纯文字按钮页面，真实截图→实际 OCR→MCP tap→页面回传命中的按钮 ID。
Frida 只用于旋转界面和临时防休眠，不修改 OCR/截图/HID 的实现；测试后恢复方向、
旋转锁与 idle timer，返回主屏幕。倒置方向只有原生 fixture 验证，没有 iPhone 倒置 UI 验证。

取消按请求携带的 session header + typed ID 匹配。现有 MCP 服务给客户端返回共享
session token；共享此 token 的客户端需要避免复用尚未结束的请求 ID。此次未重写会话系统。

## MCP 引擎专项（最终安装包）

耗时仅为该设备/页面的一次实测，不代表通用性能保证。Paddle 冷启动约 3.20 秒、
复用约 2.74 秒、单行 ROI 约 0.43 秒；Vision 该页面约 1.75 秒。

| 用例 | 状态 | 秒 |
|---|---|---:|
| legacy-default | PASS | 1.765 |
| explicit-vision | PASS | 1.746 |
| paddle-cold | PASS | 3.200 |
| paddle-warm | PASS | 2.743 |
| default-after-paddle | PASS | 1.693 |
| ocr_screen-invalid-'other' | PASS | 0.013 |
| describe_screen-invalid-'other' | PASS | 0.012 |
| ocr_screen-invalid-'' | PASS | 0.012 |
| describe_screen-invalid-'' | PASS | 0.013 |
| ocr_screen-invalid-'VISION' | PASS | 0.013 |
| describe_screen-invalid-'VISION' | PASS | 0.012 |
| ocr_screen-invalid-None | PASS | 0.011 |
| describe_screen-invalid-None | PASS | 0.011 |
| ocr_screen-invalid-1 | PASS | 0.012 |
| describe_screen-invalid-1 | PASS | 0.012 |
| ocr_screen-invalid-True | PASS | 0.011 |
| describe_screen-invalid-True | PASS | 0.011 |
| ocr_screen-invalid-[] | PASS | 0.011 |
| describe_screen-invalid-[] | PASS | 0.010 |
| ocr_screen-invalid-{} | PASS | 0.012 |
| describe_screen-invalid-{} | PASS | 0.011 |
| paddle-roi | PASS | 0.433 |
| vision-empty-roi | PASS | 0.014 |
| paddleocr-empty-roi | PASS | 0.014 |
| concurrent-vision | PASS | 2.187 |
| concurrent-paddleocr | PASS | 3.365 |
| describe-paddleocr | PASS | 3.049 |
| describe-vision | PASS | 1.963 |
| paddle-language-error-no-fallback | PASS | 0.013 |

## 完整 MCP 回归：222

按 ios-mcp-test 的先构建/安装/全量验证流程执行。最终稳定运行后的脚本汇总：
PASS 46 / FAIL 0 / SKIP 0。

注意：`input_text/type_text/press_key` 是脚本合并行；
输入内容通过 OCR 校验，`press_key delete` 的实际删除效果仍未确认，不能将其单独当作验证通过。
安装/卸载两行是错误输入 wiring 检查，不是新 IPA 的安装卸载往返；
本次 deb 的实际安装另外已经执行并确认。

| 功能点 | 状态 | 详情 |
|---|---|---|
| `HTTP /health` | PASS | ios-mcp 1.2.6 status=ok |
| `HTTP upload+download` | PASS | roundtrip 20b ok |
| `get_screen_info` | PASS | 375x667pt locked=False |
| `get_device_info` | PASS | iPhone9,3 iOS 15.8.8 batt 99% |
| `get_frontmost_app` | PASS | com.apple.springboard |
| `describe_screen` | PASS | 32 elements |
| `get_ui_elements` | PASS | 5 elems |
| `get_element_at_point` | PASS | hit-test ok |
| `ocr_screen` | PASS | 33 texts |
| `screenshot` | PASS | 76346b jpeg |
| `get_brightness` | PASS | 0.231 |
| `get_volume` | PASS | 0.125 |
| `get_clipboard` | PASS | has clipboard |
| `list_apps` | PASS | 14 apps |
| `list_running_apps` | PASS | 1 running |
| `get_app_info` | PASS | com.Alfie.TrollInstallerX.CFK4B4MHGY v1 |
| `list_dir` | PASS | 5 entries |
| `write_file` | PASS | 17 bytes |
| `read_file` | PASS | content matches |
| `run_command` | PASS | MCP_OK_42 |
| `get_crash_logs` | PASS | 30 reports |
| `read_crash_log` | PASS | 30032 chars |
| `get_syslog` | PASS | 0 error entries / 3s |
| `set_clipboard` | PASS | roundtrip ok (restored) |
| `set_brightness` | PASS | set 0.9 -> 0.9 (restored) |
| `set_volume` | PASS | set 0.9 -> 0.9 (restored) |
| `install_app(wiring)` | PASS | rejected bad path -> wired (File not found: /var/mobile/__nope__.ipa) |
| `uninstall_app(wiring)` | PASS | rejected bogus id -> wired (Uninstall failed: DEB package not installed: com.example.doe) |
| `wake_and_home` | PASS | locked=False on=True |
| `press_home` | PASS | Home button pressed (100ms) -> SpringBoard |
| `press_volume_up` | PASS | Volume Up button pressed (100ms) |
| `press_volume_down` | PASS | Volume Down button pressed (100ms) |
| `toggle_mute` | PASS | toggled twice (restored) |
| `tap_screen` | PASS | Tapped at (1.0, 1.0) |
| `tap_element` | PASS | matched & tapped '飞行模式' |
| `long_press` | PASS | Long pressed at (1.0, 1.0) for 500ms |
| `double_tap` | PASS | Double tapped at (1.0, 1.0) with 100ms interval |
| `swipe_screen` | PASS | Swiped from (200.0,500.0) to (200.0,200.0) in 300ms |
| `drag_and_drop` | PASS | scrolled (content changed) |
| `wait_for_element` | PASS | found=False waited=2.1s |
| `wait_for_disappear` | PASS | disappeared=True |
| `launch_app` | PASS | frontmost=com.apple.Preferences |
| `kill_app` | PASS | killed (not frontmost) |
| `open_url` | PASS | opened Settings (frontmost=com.apple.Preferences) |
| `input_text/type_text/press_key` | PASS | input+type OCR=ok, press_key delete=unverified |
| `press_power` | PASS | on=True -> press_power on=False -> wake on=True |

## 构建产物

这些是本地开发验证包，不是新版本发布；所有包保留原来的 1.2.6 版本号。

- `com.witchan.ios-mcp_1.2.6_iphoneos-arm.deb`: 23953406 bytes; SHA256 `196ea8c0a458fd4acfce919b10a1d2088cd805e94122c36be67129b18f5f1890`
- `com.witchan.ios-mcp_1.2.6_iphoneos-arm64.deb`: 23893458 bytes; SHA256 `f83bd39cd7b17c474b18f0e07067cfdd4dbc81d2c946875807f788ada1eec7a8`
- `com.witchan.ios-mcp_1.2.6_iphoneos-arm64e.deb`: 23892610 bytes; SHA256 `6e2054370722b0e86d9bceb957b47448543e1432b89d81865862025e239cfd34`

## 复现方式与证据

完整命令见 [PADDLEOCR.md](PADDLEOCR.md)。入口：

- `scripts/test_ocr_unit.sh`
- `tests/paddle_worker_test.py`（Mac 或 SSH 真机原生 worker）
- `tests/mcp_ocr_engines_test.py`
- `tests/paddle_lifecycle_device_test.py`（仅授权设备，故障注入后 finally 恢复模型）
- `tests/ocr_ui_device_test.py`（真实界面/横屏/点击）
- `tests/paddle_package_test.py`
- `.codex/skills/ios-mcp-test/scripts/test_ios_mcp.py`

本地原始证据位于 `.codex-session-data/paddle-build/`，不纳入 Git：
`binary-audit.json`、`package-audit.json`、`final-package-{1,2,3}.log`、
`final-engines222.json`、`final-lifecycle222.json`、`final-ui222/results.json`、
`final-native-macos.json`、`final-native222.json`、`final-full222-stable.log`。

测试期间排除的无效轮次也保留：初次 skill 安装被锁屏拦截，但旧版本号相同，
不能用健康检查的版本号宣称装上新代码；最后一次安装后立即测试又撞到异步 respring
窗口。新增安装测试脚本会检查安装返回错误，并等待新 SpringBoard PID，
避免将旧进程的短暂 /health 响应当成安装完成。

实际发现并修正的新增实现问题：CGImage 解码不应多做垂直翻转；
SpringBoard 对 Unix socket 的 poll 返回 EPERM 时使用有界 select；
spawn 源 FD 避开 0/1/2；成功请求的旧初始化警告不带入后续取消错误。
