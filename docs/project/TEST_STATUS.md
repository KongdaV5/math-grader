# P1-W1 测试状态

## 基线

- Start branch：`main`
- Start SHA：`0ffc4b7ff336d33f8836fbb9f998daea5443c4fe`
- Implementation End SHA：`cd1114122396f2f8c11df3abef71d468e012abe1`
- 开始修改前 `.venv/bin/python -m pytest`：**28 passed**（P0-W1 基线）

## 环境

- Python：3.9.6
- pytest：8.4.2
- jsonschema：4.25.1
- Node：24.21.0
- Tauri JS API / CLI：2.11.1 / 2.11.5
- Rust：1.98.1（隔离安装到 `/tmp`，未改用户全局 PATH）
- Xcode：16.4

## 最终验证

- `.venv/bin/python -m pytest`：**40 passed**，包括原 P0-W1 28 项和 P1 新增 12 项；
- `.venv/bin/python -m compileall -q benchmark local_service tests`：**PASS**；
- `.venv/bin/python -m local_service --help`：**PASS**；
- `npm run typecheck`（`desktop/`）：**PASS**；
- `npm run build`（`desktop/`）：**PASS**；
- `cargo check`（`desktop/src-tauri/`）：**PASS**；
- `npm run desktop:dev`：**PASS**，Tauri 原生进程启动并拉起本地 Python 服务；
- `npm run desktop:build`：**PASS**，生成 macOS `Math Grader.app`；
- 从打包 `.app` 启动后请求 `http://127.0.0.1:8765/health`：**PASS**；
- `npm run demo:dev` 浏览器 UI：新建班级、学生、作业 → 开始 Submission → 添加占位页 → 完成该生 → UI 显示 `COMPLETED` 与 Mock Provider 结果：**PASS**；
- `git diff --check`：**PASS**；
- `npm install` audit：**0 vulnerabilities**。

## P1 新增测试覆盖

- SQLite migration / schema 初始化；Class / Student / Assignment 创建和读取；
- Student 与 Assignment 的 Class 归属校验；
- Submission 创建、多页添加、page_count、图片落盘；
- 全部合法状态迁移，以及 `EMPTY → PROCESSING` 与错误 finish 拒绝；
- finish 原子地进入 READY / QUEUED；worker 调用 Mock、持久化 RecognitionResult 并完成 Submission；
- 多 Submission FIFO 顺序处理；一个任务失败后错误被记录且后续任务继续；
- Provider route/fallback 与 Provider Registry 扩展；
- 本地 HTTP server + worker 的完整 API smoke 和状态码验证。

## 已知验证边界

- 机器屏幕在原生 app 启动时处于锁定状态，无法用 GUI 辅助功能树读取原生窗口内容；Tauri 原生进程、打包 app 和服务健康响应已验证，React UI 与服务的交互闭环在浏览器中完整验证。
- `.app` 使用系统 `python3` 启动打包的服务代码，因此运行机器需有 Python 3.9+。
- 没有真实 OCR/VLM 或真实作业数据测试；这属于 P5 / P6 后续阶段。

---

# P2 Capture Bridge 测试状态

## 基线与版本

- Start branch：`phase/p1`
- Start SHA：`83305d6f94d144ff2261340ad91f9b565ab071ad`
- Implementation branch：`phase/p2`
- Implementation End SHA：`37887fd3df772a0440580ca384843388a2de9e71`
- Python：3.9.6；Node：24.21.0；Rust：1.98.1（Rust 工具链隔离安装于 `/tmp`）。

## 自动验证

- `.venv/bin/python -m pytest -q`：**51 passed**（P1 原 40 项 + P2 新增 11 项）；
- `.venv/bin/python -m compileall -q local_service tests`：**PASS**；
- `.venv/bin/python -m local_service --help`：**PASS**；
- `npm run typecheck`：**PASS**；`npm run build`：**PASS**；
- `cargo check`：**PASS**；`npm run desktop:dev`：**PASS**，Tauri dev 进程启动且本地服务 `/health` 返回 `ok`；
- `npm run desktop:build`：**PASS**，生成 `Math Grader.app`；Capture 手机网页已随服务资源纳入 bundle；
- `git diff --check` 与 staged diff 检查：**PASS**。

## P2 自动测试覆盖

- LAN 地址发现优先 Wi-Fi，并忽略 VPN benchmark 范围；Session token hash、失效/过期/结束/进程重启；
- 多页图片上传及 metadata、UUID 幂等、MIME/签名/空文件/大小校验、删除和 page_index 重排、磁盘安全路径；
- 当前 Submission 校验、防迟到上传串学生、跨 Submission 页面访问拒绝；
- “完成该生”前不推进；确认后进入队列且只创建一个任务；前一位 PROCESSING 时下一位 CAPTURING；最后一位完成后不循环；
- HTTP Capture 面 Host/Origin/token、路由隔离、上传/读取/删除/finish/session end；Desktop admin 非 loopback 监听拒绝；Session 过期后 Capture listener 关闭。

## Browser E2E 与验收边界

- 已完成浏览器实际操作：Desktop UI 建立临时班级、两名学生和作业并开启 Session；二维码不含 roster 信息；手机等价页面预览重拍后不增加页数；逐页上传 3 张本地 PNG；取消删除确认保留页面；删除中间页后余下页重新编号，再补传并刷新恢复三页。
- Finish E2E：确认完成首位学生后，手机页自动切换到第二位；第二位上传一页后，Mac 显示当前归属为第二位且首位处于 `排队中`。为验证可见队列，使用无 worker 的临时测试服务；最后一位完成后，手机页显示“本班拍摄完成”，Mac 显示 2/2 和两位学生均 `排队中`。
- 已在 Desktop UI 结束 Session；临时 Capture listener 已关闭。真实 iPhone Safari：**未测试**；测试图片是无真实学生内容的本地 1×1 PNG fixture，保存在 `/tmp`，未提交 Git。
- 桌面浏览器 UI E2E 已通过，当前状态为 **READY_FOR_DEVICE_TEST**；真实 iPhone Safari 通过后方可将 P2 标记 PASS。

## Release 风险

- 保留 P1 已知正式发布阻塞：打包 `.app` 通过系统 `python3` 启动服务，目标 Mac 需要 PATH 中有 Python 3.9+；P2 未改运行时打包架构。

---

# P3-X1 Product Framework & Model Runtime Foundation 测试状态

## 基线与版本

- Start branch：`phase/p2`，Start SHA：`cc871a733fb942e42d3e156282596f31212312d0`；Implementation branch：`phase/p3-x1`。
- Implementation End SHA：`06cd1e3035e2b870ea208efd080f68810e6929b6`。
- 开始修改前 Python 全套：**51 passed**；最终：**73 passed**，新增 P3-X1 22 个用例，P0/P1/P2 原 51 项全通过。
- Python 3.9.6、Node 24.21.0、Rust 1.98.1。当前 Rust 工具链从 Homebrew 安装于本机；这是开发验证环境变更，不进入项目源码。

## 自动化验证

- `.venv/bin/python -m pytest -q`：**73 passed**。
- `.venv/bin/python -m compileall -q benchmark local_service tests`：**PASS**。
- `.venv/bin/python -m local_service --help`：**PASS**。
- `npm run typecheck`、`npm run build`：**PASS**。
- `cargo check -q`、`npm run desktop:dev`：**PASS**；Tauri dev 启动后 `/health` 返回 `ok` 与 Python 3.9.6。
- `npm run desktop:build`：**PASS**；macOS `.app` 内包含新增模型清单、模板 migration 与页面资源。
- 打包 `.app` 直接启动：**PASS**；`/health`、标准路径选择、原生窗口的首页、模型中心、模板、设置页面均实际检查。
- `git diff --check`：**PASS**。

## P3-X1 新测试覆盖

- Catalog schema、重复 ID、未知 Provider、非法路径；ModelManager 未安装/真实文件计数进度/取消/失败/重试/原子安装/磁盘不足/路径约束/验证/删除。
- Provider Registry、未安装错误、健康检查与模型加载错误；Recognition model route 不存在与能力不兼容。
- Template migration 从 P2 数据升级且保留原班级、TemplateGroup/PageTemplate/Question/AnswerRegion CRUD、0..1 坐标校验。
- ImagePipeline 合成正常/旋转/透视/模糊/过暗/过曝/无页面图片以及 EXIF 方向；原图字节不变。
- 自动测试只使用 tiny fake downloader，不下载大型模型。

## 真实下载与 UI smoke

- 从 PaddlePaddle 官方 Hugging Face Small det/rec 仓库真实获取 6 个指定文件，总计 **31,628,665 bytes**；解析并记录两个 repo 的 commit SHA，安装清单验证通过，ONNX Runtime 两个 session 均加载成功，之后卸载并删除。GUI 模型中心实际显示 `NOT_INSTALLED → DOWNLOADING → INSTALLED → NOT_INSTALLED`，健康检查识别安装状态。未下载 Formula、4B、8B。
- PaddleOCR 官方 `general_ocr_002.png` 示例图真实读取并经 ImagePipeline 输出；对该图片调用已加载的 PPOCRONNXProvider 明确返回 `PROVIDER_UNAVAILABLE`，因为检测/识别后处理未集成。此处没有 OCR 文本推理成功证据。
- 浏览器九页导航、首页真实统计、模型中心、模板组/参考页创建及合成参考图导入、Question/AnswerRegion 展示、设置页运行路径均实际检查。
- P2 Browser E2E 回归：合成班级两名学生、QR/独立 Capture 页、预览重拍不增加页数、三页即时上传、删除中间页后余下页码整理、刷新恢复、补拍、确认 finish、自动下一学生、第二名页面归属、后台 2 个 Job 完成和全班完成。临时 Session 已结束，测试数据库/图片/模型均已清理；真实 iPhone Safari 仍未测试。

## 边界

- PP-OCR ONNX 模型可真实加载，但尚无检测后处理与识别拼接；Formula 只具备检测/依赖/错误接口；MLX VLM 用本地安装路径的适配器尚无权重实测。Submission 默认仍经 Mock Provider。
- `.app` 继续由系统 Python 3.9+ 启动；正式发布仍需解决 Python 及 Python 依赖随包交付。
