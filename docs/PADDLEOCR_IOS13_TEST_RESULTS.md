# iOS 13.5.1 真机 OCR 补测（2026-09-26）

历史构建记录：本页对应“默认 Vision”的包与测试。之后按用户要求改为默认 PaddleOCR，
最新默认行为与验证见 [默认引擎变更报告](PADDLEOCR_DEFAULT_ENGINE_TEST_RESULTS.md)，本页原始结果不回写。

## 设备与构建

- 地址：`192.168.1.17`；iPhone 7 Plus / iPhone9,2 / A10 / iOS 13.5.1（17F80）。
- 越狱：rootful；原安装 iOS MCP 1.0.1，本次升级为当前工作区的 1.2.6 正式模式包。
- 根据 ios-mcp-test 流程先构建、审计、安装、确认新进程和接口，再做实际 OCR 验证。
  原 1.0.1 的 `install_app` 只声明支持 IPA，本次使用 SSH + `dpkg -i` 安装 deb，再执行 sbreload。
- 安装前旧插件文件已备份到本地 `pre-upgrade-files.tar.gz`；服务恢复后 SpringBoard PID
  从 2431 变为 2782，健康接口版本和 OCR engine Schema 均确认更新。
- 本次只增加测试脚本与报告，**没有修改生产 OCR、模型、默认值、权限或版本号**；未提交、推送或发版。

```sh
printf '1\n1\n' | ./build.sh
python3 tests/paddle_package_test.py --arch arm --out PATH/package-audit.json
python3 scripts/check_paddle_binaries.py --out PATH/binary-audit.json
bash scripts/test_ocr_unit.sh
```

包：`packages/com.witchan.ios-mcp_1.2.6_iphoneos-arm.deb`，23,648,884 字节。
SHA256：`029941e71a97fc14545926bc4ac717c26657d86eabfb7af32b811b393baf5454`。
本次重新构建替换了 packages 中的上一份同名 rootful 产物；旧包已保存在本轮日志目录
`previous-rootful.deb`，之前三设备报告中的旧哈希是历史构建哈希。

ONNX Runtime 1.20.1、PP-OCRv5_mobile、OpenCV 4.10.0、Clipper 6.4.2 保持不变。
worker/ORT/OpenCV 的实际 Mach-O/归档成员为 arm64、minos=13.0；ORT 静态链接到 worker，
无独立 ORT dylib，无 Vision/CoreML/Metal 推理依赖。实际 MCP 推理返回 CPUExecutionProvider。
主 tweak、worker、两个模型与字典的安装后 SHA256 均与本次 deb 一致。
原项目的 linker、旧 libzip/helper/libcrypto 警告仍在，不代表所有非 OCR 功能均通过 iOS 13 认证。

## 验收范围与结果

仅用第三方应用页面：Cydia、同花顺、FirstApp。没有用系统设置或 Safari 页面替代。
未登录账号、交易、接受推送授权、安装 Cydia 软件包或修改应用配置。
原生 worker 的固定图片另用于算法方向测试，不冒充第三方界面或物理横屏测试。

| 功能点 | 结果 | 实际证据 |
|---|---|---|
| 新包安装及服务启动 | PASS | 新 SpringBoard PID，1.2.6 health、engine Schema 正常 |
| 旧调用不传 engine | PASS | Vision，revision 1，en-US，fast，实际识别英文 |
| 显式 engine=vision | PASS | 同样为 revision 1 英文识别 |
| Vision 英文 accurate | PASS | 显式/省略 engine 均可，CPU-only accurate 路径执行 |
| Vision 明确请求中文 | PASS | 简体/繁体/中英混合 × fast/accurate × 显式/省略 engine，12 种均返回不支持错误 |
| Paddle 中文、英文、数字 | PASS | 当前系统真实 CPU 推理，不是编译成功或引擎替身 |
| Paddle 冷/热调用 | PASS | 重复请求复用 worker PID 2803 |
| Paddle 后省略 engine | PASS | 仍为 Vision revision 1 / en-US / fast |
| 两引擎并发 | PASS | 各自返回正确引擎，不串用 |
| 非法 engine | PASS | 8 类值 × 两工具，返回 -32602 |
| 不支持语言、不回退 | PASS | 对应引擎错误，不静默换引擎 |
| describe_screen 两引擎及默认值 | PASS | OCR 分支正确；稳定后也返回 32 个 AX 元素 |
| ROI、屏外空 ROI | PASS | 正常区域文字与坐标、两引擎空区域结果正确 |
| 非法 ROI | PASS | 7 类 × 两引擎，返回 -32602 |
| 超屏 ROI | PASS | 两引擎正常裁剪并返回合法坐标 |
| JPEG 截图与逻辑点尺寸 | PASS | JPEG 实际解码，414×736；截图已人工查看 |
| Cydia OCR→ROI→tap | PASS | Paddle 两次中文 tab，Vision 两次英文 Cydia tab，4 次均命中 |
| FirstApp 宽裕 ROI 导航 | PASS | Paddle 20 点留白的 ROI，“个人中心→首页”两次命中 |
| FirstApp 很窄 ROI | FAIL（漏检） | 8 点留白返回空；整屏或 20/40 点留白可识别，未修复算法 |
| 固定图片四方向 | PASS | 真机原生 worker orientation 1/3/6/8，中文/英文/数字、已知中心与 ROI |
| CTC 阈值、空白、坏图恢复 | PASS | 真机原生 worker 实际推理 |
| 模型缺失、无回退、恢复 | PASS | Paddle 明确 missing；Vision 仍识别出 13 段文字；还原后 Paddle 正常 |
| 热会话模型损坏、无回退、恢复 | PASS | checksum mismatch；Vision 可用；原始 SHA256 恢复后 Paddle 正常 |
| Paddle 并发上限 | PASS | 第二个请求 busy、队列上限 0，同时 Vision 正常 |
| 取消与 session 隔离 | PASS | 错误 session 不误取消；正确取消后 worker PID 消失 |
| 超时 | PASS | 30.045 秒返回错误，worker PID 已消失 |
| HTTP 断连 | PASS | 对应 worker 退出，随后双引擎正常 |
| 故障后恢复 | PASS | 两引擎继续识别当前第三方页面 |
| 物理横屏 UI | SKIP | 本设备本轮未旋转第三方界面；不能用图片旋转替代 |
| iOS 13.0 / 其他 iOS 13 机型 | SKIP | 本次仅 13.5.1 / iPhone9,2，不外推所有小版本/硬件 |
| 全量 MCP、长期压力、Display Zoom | SKIP | 本轮是 OCR 兼容性专项 |

接口通用回归 `mcp_ocr_engines_test.py` 为 29 项；新增
`ocr_ios13_device_test.py` 为 37 项，全部通过。两者有部分覆盖重叠，不应当作 66 个独立功能。
`paddle_lifecycle_device_test.py` 的 7 项生命周期检查也全部通过。
资源损坏测试后再次逐文件核对安装内容，主 tweak、worker、两个模型与字典仍与 deb
SHA256 完全相等；目录中无测试备份残留。收尾再次执行 Paddle CPU 和随后默认 Vision，
均成功，AX 查询也恢复正常；health 正常，设备已返回主屏幕。
SpringBoard PID 仍为安装后的 2782，本轮测试期间未观察到额外重启。

Vision 中文错误实例如下；不是自动转成英文后输出乱码，也不是转用 Paddle：

```text
vision OCR failed: OCR languages ("zh-Hans") are not supported by Vision revision 1
on this device. Supported languages: ("en-US")
```

这台设备 `UIScreen.scale=3`、`native_scale≈2.6087`、帧缓冲 1080×1920、逻辑点 414×736。
两引擎返回坐标直接用于 tap，无额外除以 3 或 nativeScale。
Cydia 实际点击点：软件源 `(124,728)`、已安装 `(289,728)`、Cydia `(41,730)`。

## 文字与 ROI 的实际限制

| 页面/引擎 | 选定可见标签命中 | 说明 |
|---|---:|---|
| Cydia / Vision | 7/7 | 英文标签，不要求 iOS 13 Vision 识别中文 |
| Cydia / Paddle | 13/13 | 英文与中文标签 |
| 同花顺首页 / Paddle | 14/14 | 中文菜单、0%、序号与百分比数字 |
| FirstApp 首页 / Paddle | 3/3 | 首页、添加商品、个人中心 |

这是人工核对截图后的有限标签抽查，不是整页字符准确率。图标、小字、标点和形似字符
仍可能误识，不能描述为通用“100% 准确”。同花顺首次截图是应用内推送提示，
再次打开时该提示已自行消失；第一轮与旧提示文案比较的结果不计入准确率，
保留原始记录后按实际首页重新定义参考文字并重新截图、识别。

FirstApp 的“个人中心”位于底部，小字在整屏可识别，但非常窄的裁剪区域返回空数组。
留白由 8 点增至 20/40 点后同引擎识别成功；20 点留白返回的点位也实际命中导航。
失败 ROI 为 `(x=280,y=711,width=61,height=25)`；成功 ROI 为
`(268,699,85,37)` 和 `(248,679,125,57)`，均为 fixed 逻辑点。
这是本轮复现的 **Paddle ROI 漏检边界**，不因扩大 ROI 能用就记为原始用例通过。
未在本次测试中调整检测阈值、放宽校验或修改模型/预处理。

此前 223 Telegram 的超长英文行宽度上限问题也未被这次 iOS 13 验证修复，
见 [三设备报告](PADDLEOCR_THREE_DEVICE_TEST_RESULTS.md)。

## 测试过程中的非 OCR 断言修正

- 安装后首次 Cydia `get_ui_elements` 返回 AX inactive/timeout；后续 describe_screen
  返回 32 个元素。该初次超时保留在日志，不能声称首次 AX 查询也通过。
- Cydia 的“已安装”tab 记住了原先的包详情页面，顶部不是固定标题“已安装”，
  而是“详情”与返回“已安装”。截图确认导航已发生后修正断言，没有修改产品代码。
- FirstApp 个人页实际显示“未登录”，不是顶部标题“个人中心”；同样先查看截图再修正
  测试断言。没有点击登录、退出登录或设置。原始失败日志保留，不将错误页面预期当成坐标故障。

## 可执行测试与证据

```sh
python3 tests/mcp_ocr_engines_test.py --url http://192.168.1.17:8090/mcp --out engines.json
python3 tests/ocr_ios13_device_test.py --url http://192.168.1.17:8090/mcp --out ios13-compat.json
SSHPASS=YOUR_TEST_DEVICE_PASSWORD python3 tests/paddle_lifecycle_device_test.py \
  --url http://192.168.1.17:8090/mcp --ssh root@192.168.1.17 \
  --resources /usr/share/ios-mcp/paddleocr --app-bundle-id com.saurik.Cydia --out lifecycle.json
```

先打开 Cydia 有英文文字的首页，再执行接口测试。原生 worker 图像测试使用
`paddle_worker_test.py --worker 'SSH_COMMAND /usr/libexec/ios-mcp/mcp-ocr-worker'`
及设备的 `--resources /usr/share/ios-mcp/paddleocr --skip-resource-tests`。
该测试把固定输入传到真机执行，不在 Mac 上代跑识别；资源故障另通过 MCP 注入。

本地证据目录：`.codex-session-data/ocr-ios13.0yJIQ9/`，包括构建/安装日志、
`package-audit.json`、`binary-audit.json`、`installed-integrity.json`、`engines.json`、
`ios13-compat.json`、`native-worker.json`、`samples.json`、`taps.json`、
`firstapp-roi.json`、`lifecycle.json`、`corrupt-resource.json`、`final-state.json` 及截图。
用户应用截图不纳入公开仓库。

本次支持的结论是：当前静态链接实现已经在 **iOS 13.5.1 真机实际运行并通过上述兼容性项**；
不是对 iOS 13.0、全部机型、所有页面或原有全部 MCP 功能的无限制兼容承诺。
