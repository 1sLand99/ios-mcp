# OCR 三设备正式模式包回归（2026-09-25 至 2026-09-26）

后续补测：192.168.1.17 / iOS 13.5.1 已安装重新构建的 rootful 包，实际结果见
[iOS 13.5.1 真机报告](PADDLEOCR_IOS13_TEST_RESULTS.md)。本页保留三设备当时的结果和包哈希。
packages 中同名 rootful 包之后已重新构建，旧包另存于后续日志目录 `previous-rootful.deb`。

## 结论与范围

三个 scheme 均从当前工作区重新构建正式模式 deb，并安装到对应设备。
本轮验证此前的 ORT 静态链接兼容性修复，未改动生产 OCR 算法、模型、引擎默认值或版本号。
版本仍为 `1.2.6`；这是本地正式构建模式，不表示已创建或发布 GitHub Release。
未执行 Git 暂存、提交、推送、分支或 tag 操作。

按用户追加要求，**本报告的应用页面验收只计第三方应用**。
此前已跑的系统设置/Safari 页面结果不充当本轮第三方应用结果。
执行遵循 ios-mcp-test 的先构建、安装、确认生效、再验证实际效果的流程，
覆盖范围按用户要求限定为 OCR 及相关截图、引擎路由、坐标、生命周期，不是全量 MCP 回归。

| 设备 | 实际机型与系统 | 安装包 | 第三方应用 |
|---|---|---|---|
| 192.168.1.221 | iPhone SE 第二代 / iPhone12,8 / iOS 14.3 | rootful | 抖音、iOSAutomator、Shadowrocket |
| 192.168.1.222 | iPhone 7 / iPhone9,3 / iOS 15.8.8 | roothide | 微信、Shadowrocket |
| 192.168.1.223 | iPad7,11 / iPadOS 18.3.2 | rootless | Telegram、豆包、Shadowrocket |

三台各有 29 项接口检查、31 项额外参数/资源检查、7 项生命周期检查通过，
另有每台 4 次第三方应用实际 OCR→ROI→tap 导航命中。
223 在用户手动转到横屏后，另补测两引擎共 4 次横屏 ROI 导航，全部命中。
这些通过项**不意味着任意页面识别无误**：Vision 有一处抽查文字误识，
Paddle 在 Telegram 的一条长英文 ROI 上触发了宽度限制，详见下文。

**这轮三设备测试当时尚未完成 iOS 13 真机验证**。三台系统分别为 14.3、15.8.8、18.3.2，
不能用这些结果或 minos=13.0 的编译检查替代 iOS 13 实际运行验收。

## 构建、安装和完整性

```sh
printf '1\n1\n' | ./build.sh
printf '2\n1\n' | ./build.sh
printf '3\n1\n' | ./build.sh
python3 tests/paddle_package_test.py --version 1.2.6
python3 scripts/check_paddle_binaries.py
bash scripts/test_ocr_unit.sh
```

三次构建均为 `FINALPACKAGE=1 DEBUG=0 STRIP=1`。实际 deb、模型字典校验值、
许可证、安装目录及 Mach-O 审计通过。既有的 `-multiply_defined`、arm64e deployment、
libzip 平台信息和旧 helper/libcrypto 链接警告仍存在，不宣称整个工程零警告。

依赖仍为 ONNX Runtime 1.20.1 CPU 静态库、PP-OCRv5_mobile 检测/识别模型、
OpenCV 4.10.0 core/imgproc、Clipper 6.4.2。精确来源/版本/哈希见
`third_party/paddleocr/dependencies.lock.json` 及 [构建说明](PADDLEOCR.md)。
worker 与 ORT/OpenCV archive 成员为 arm64、minos=13.0；worker 不链接 ORT 动态库、
Vision、CoreML 或 Metal。实际 Paddle 请求均返回 `CPUExecutionProvider`，
生产 worker 初始化还会核验可用 EP 列表；这不是只看 engine 名称推断 CPU。

通过 `tests/install_test_package.py` 上传/安装各自包，等待新的 SpringBoard PID
和服务恢复后才开始测试。安装后二进制、主 tweak、两个模型与字典均与 deb 对照。
221/223 对照文件 SHA256 一致；222 RootHide 会为 Mach-O 写入设备 brand 并更新签名，
所以不能直接要求整个文件哈希相等。逐字节对照仅放行已定位的 section-name 零填充区
8 字节 brand 与代码签名范围；其余内容必须完全一致，代码/数据 payload 未变化。
模型与字典仍要求完整 SHA256 相等，未放宽。

| scheme / 文件（位于 `packages/`） | 字节数 | SHA256 |
|---|---:|---|
| rootful / `com.witchan.ios-mcp_1.2.6_iphoneos-arm.deb` | 23677990 | `7a37e17049d5f3ff36d58a000479a12c74d74c73c714f2bb24aee68ee16d404d` |
| rootless / `com.witchan.ios-mcp_1.2.6_iphoneos-arm64.deb` | 23612742 | `04608b86d38744a236e905b2518b3bc415a5a0a3bbf0bc5f73a93688dd87ae8f` |
| roothide / `com.witchan.ios-mcp_1.2.6_iphoneos-arm64e.deb` | 23625122 | `21572b05cc67f47e717023bff10fc05b37f1952fd677bacd323518a78902e0a2` |

## 每台设备功能结果

以下接口、边界和故障测试的 OCR 页面均为 Shadowrocket。
PASS 包含结果断言，不只是 HTTP 请求未报错。每个原始测试 case 的请求/结果在本地 JSON 中保留。

| 功能点 | 221 | 222 | 223 | 验证内容 |
|---|---|---|---|---|
| OCR Schema | PASS | PASS | PASS | 两工具 engine 可选、枚举 vision/paddleocr |
| 不传 engine | PASS | PASS | PASS | 默认 Vision，返回实际文字 |
| 显式 vision | PASS | PASS | PASS | 仍走 Vision |
| 显式 paddleocr 冷/热调用 | PASS | PASS | PASS | CPU EP，同一 worker PID 复用 |
| Paddle 后省略 engine | PASS | PASS | PASS | 仍为 Vision，无偏好残留 |
| 非法 engine | PASS | PASS | PASS | 8 类值 × 两工具，均为 -32602 |
| 两引擎并发 | PASS | PASS | PASS | 不串引擎 |
| describe_screen 两引擎 | PASS | PASS | PASS | ocr_recognition 标识实际分支 |
| describe_screen 默认值复测 | PASS | PASS | PASS | Paddle 后省略仍为 Vision |
| Vision 英文 fast/accurate | PASS | PASS | PASS | 两级别分别执行 |
| Vision 中文+英文 accurate/fast | PASS | PASS | PASS | fast 按语言支持情况明确升 accurate |
| Paddle fast=true/false | PASS | PASS | PASS | 固定 mobile 模型，披露实际模式 |
| 两引擎不支持的语言 | PASS | PASS | PASS | 明确错误、不回退；随后默认 Vision 正常 |
| ROI 识别 | PASS | PASS | PASS | 实际文字，点位落在请求范围内 |
| 屏外空 ROI | PASS | PASS | PASS | 两引擎均为空结果 |
| 非法 ROI | PASS | PASS | PASS | 7 类输入 × 两引擎，-32602 |
| 超屏 ROI 裁剪 | PASS | PASS | PASS | 两引擎均能返回合法屏内坐标 |
| 非法置信度类型 | PASS | PASS | PASS | 字符串/数组/对象，-32602 |
| 截图 JPEG | PASS | PASS | PASS | base64 可解码显示，实际 JPEG、尺寸等于 fixed 点空间 |
| 模型缺失 | PASS | PASS | PASS | Paddle 报错、不回退；Vision 可用 |
| 模型恢复 | PASS | PASS | PASS | Paddle 恢复识别 |
| 热会话模型损坏 | PASS | PASS | PASS | checksum mismatch，不使用缓存掩盖损坏；Vision 可用 |
| 损坏测试还原 | PASS | PASS | PASS | 原始 SHA256 完全恢复，Paddle 可用 |
| Paddle 并发上限 | PASS | PASS | PASS | 第二个 Paddle busy，Vision 不被该槽位阻塞 |
| 取消与 session/ID 隔离 | PASS | PASS | PASS | 错误 session 不误取消，正确取消终止 worker |
| 30 秒超时 | PASS | PASS | PASS | 返回后检查 worker PID 已消失 |
| HTTP 断连 | PASS | PASS | PASS | 终止对应 worker，不遗留推理 |
| 故障后的双引擎恢复 | PASS | PASS | PASS | 均重新识别页面 |
| 竖屏 OCR→ROI→tap | PASS | PASS | PASS | 每引擎 app Settings→Home，共 4 次/台 |
| 横屏第三方应用 | SKIP | SKIP | PASS | 221/222 本轮未物理横屏；223 用户手动旋转后，两引擎各 2 次导航命中 |
| 全部 MCP 工具 | SKIP | SKIP | SKIP | 本次仅 OCR 专项，不是完整 46 工具回归 |
| 长期压力、Display Zoom | SKIP | SKIP | SKIP | 未在本轮覆盖 |

超时注入实际耗时：221 为 30.044 秒、222 为 30.040 秒、223 为 30.040 秒。
临时缺失/损坏模型均已恢复；这类故障为有意注入，不是正常运行发现的模型损坏。
生命周期脚本使用 `--app-bundle-id com.liguangming.Shadowrocket`，不跳到系统设置测试。
收尾再次确认三台资源目录无测试备份残留、Paddle CPU 推理成功、随后不传 engine
仍为 Vision、HTTP health 正常，并均已返回主屏幕。

竖屏点击完全使用 OCR 返回的 fixed-point `tap`，没有再除 Retina scale。
目标是 Shadowrocket 的底部导航“设置/Settings”和“首页/Home”，
通过随后页面标题、Not Connected/未连接文字和前台 bundleId 验证真实导航。
没有触碰 VPN 连接开关、发送聊天、执行付费/登录或修改账号配置。

223 手动横屏实际为 `landscape_left`：Vision 的 Settings/Home 点击点为
`(6,945)` / `(7,135)`，Paddle 为 `(7,945)` / `(7,134)`。这些仍是
`810×1080` 的 **fixed** 坐标；横屏界面映射后标签位于截图左侧，不是坐标偏移。
四次点击均验证了真实页面切换。横屏全图同时检出英文 `Not Connected`、
中文“套餐到期”和数字日期 `2026-10-18`。截图也已人工查看确认横屏内容。
本轮未覆盖反向横屏、倒置及 221/222 的第三方横屏，不能外推为所有旋转场景通过。

## 第三方页面文字抽查

方法：截图人工核对选定的可见标签，再与 OCR 文字做 NFKC、忽略空白和大小写的匹配。
这是小样本标签命中检查，**不是整页字符准确率/CER，也不是通用准确率**。
未计分文字仍可存在错误；例如图标会被识别为字符、小字/标点会变化。

| 设备 / 页面 | Vision 命中 | Paddle 命中 | ROI |
|---|---:|---:|---|
| 221 / 抖音“发现抖音朋友”页内弹层 | 6/6 | 6/6 | 两者通过 |
| 221 / iOSAutomator 英文表单 | 10/11 | 11/11 | 两者通过 |
| 221 / Shadowrocket 英文首页 | 8/8 | 8/8 | 两者通过 |
| 222 / 微信中文主页面 | 7/7 | 7/7 | 两者通过 |
| 222 / Shadowrocket 中英数字首页 | 9/9 | 9/9 | 两者通过 |
| 223 / Telegram 英文 SMS Fee 页 | 7/7 | 7/7 | Vision 通过；Paddle 长行失败，短标题通过 |
| 223 / 豆包中外文内容页 | 13/13* | 13/13* | 两者通过 |
| 223 / Shadowrocket 中英数字首页 | 9/9 | 9/9 | 两者通过 |

有效抽查标签共 70 个，Vision 命中 69 个，Paddle 命中 70 个；不要将其描述为
“Paddle 中文识别准确率 100%”。两引擎的 confidence 也未被当作等价概率比较。

*豆包原始 15 项基准中，两项不符合实际截图：手工写成“区别小说明”，实际为
“区分小说明”；动态建议“帮我写作”已不在画面，显示的是“豆包P图”。两引擎都读出了
截图上的正确文字。原始 13/15 结果未覆盖，人工复核另存 `sample-review.json`，
本表仅计算剩下 13 个有效基准，不把基准错误记成 OCR 漏识。

### 发现的限制/错误

1. **Vision 字符混淆**：221 iOSAutomator 的 `Data API URL` 被读成 `Data APl URL`
   （大写 I / 小写 l）。同页 Paddle 匹配正确。这是识别误差，不是接口或坐标故障。
2. **Paddle 长行 ROI 请求失败**：223 Telegram 整屏成功，但围住长英文说明的窄 ROI
   返回 `text line too wide (2048 normalized pixels); use a smaller region`。
   同一页面改为 `SMS Fee` 短标题 ROI，Paddle 成功且坐标在 ROI 内，无 Vision 回退。
   对应 `mcp-ocr-worker/PaddleOCR.mm` 中 `ceil(48 * line.cols / line.rows) <= 2048`
   的硬上限：ROI 改变检测框/裁剪后，细长文字行可能超过限额，导致本次请求整体失败。
   这不是 2048 点屏幕坐标上限。此次测试没有直接提高限额或改生产代码。
   如需支持该场景，应另做长行切段识别与拼接，并验证边界字符、坐标、内存和超时，
   不建议仅取消内存保护。正式对外发版前需要明确是否接受这一限制。

## 耗时观察

下表是上述真实页面的单次 MCP 端到端调用秒数，包含截图/传输/识别开销。
不是多次均值，不保证全部为同一冷/热状态，也不能跨设备不同页面直接排名。
默认参数在这些系统上因中文语言支持走 Vision accurate；不是纯英文 fast 的性能。

| 设备 / 页面 | Vision 秒 | Paddle 秒 |
|---|---:|---:|
| 221 / 抖音 | 0.709 | 2.088 |
| 221 / iOSAutomator | 0.862 | 2.072 |
| 221 / Shadowrocket | 0.685 | 2.695 |
| 222 / 微信 | 2.020 | 3.298 |
| 222 / Shadowrocket | 2.359 | 4.084 |
| 223 / Telegram | 3.214 | 3.480 |
| 223 / 豆包 | 4.195 | 3.828 |
| 223 / Shadowrocket | 3.785 | 5.998 |

## 证据及复跑

本地忽略目录：`.codex-session-data/ocr-three-release.3yfVde/`。
截图可能包含测试设备上的个人内容，因此不纳入公开文档或提交。

- `build-{1,2,3}.log`、`packages.json`、`binaries.json`：本次构建与二进制检查。
- `{221,222,223}-install.log`：安装及服务恢复。
- `installed-integrity.json`、`222-roothide-brand-audit.json`：安装内容对照。
- `{N}-thirdparty-engines.json`：29 项接口结果及耗时。
- `{N}-extra.json`：31 项额外检查结果。
- `{N}-thirdparty-lifecycle.json`：7 项故障隔离结果。
- `thirdparty/{N}-tabs.json` 及截图：每台 4 次真实 ROI 导航点击。
- `thirdparty/223-manual-landscape.json` 及截图：223 手动横屏 4 次真实 ROI 导航点击。
- `thirdparty/samples.json`、`thirdparty/sample-review.json`、各 `*-sample.jpg`：文字、ROI、实际错误与人工复核。
- `thirdparty-summary.json`：各设备核心测试组状态。
- `{N}-final-thirdparty.json`：收尾模型状态、CPU/default Vision、health 和返回主屏幕。

公共测试脚本的复跑示例（先安装匹配 scheme 的本次 deb，再打开第三方文字页面）：

```sh
python3 tests/install_test_package.py --url http://DEVICE:8090/mcp packages/MATCHING.deb
python3 tests/mcp_ocr_engines_test.py --url http://DEVICE:8090/mcp --out engines.json
SSHPASS=YOUR_TEST_DEVICE_PASSWORD python3 tests/paddle_lifecycle_device_test.py \
  --url http://DEVICE:8090/mcp --ssh root@DEVICE \
  --resources RESOLVED_JAILBREAK_ROOT/usr/share/ios-mcp/paddleocr \
  --app-bundle-id com.liguangming.Shadowrocket --out lifecycle.json
```

原始运行中遇到的启动画面、广告和系统权限弹窗不作为“第三方页面识别成功”。
微信初次地球启动画面未纳入标签结果，等待主页面后重测；不为完成测试登录或付费。
