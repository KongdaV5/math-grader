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

---

# P4-X1 Template → Crop → Real Recognition → Result Inspection 测试状态

## 基线与自动化

- Branch：`phase/p4-x1`，Start SHA：`fa9564d5a5ad47f6dffcd52914d0546f18e41589`；开始前 P0–P3 Python **73 passed**。
- Implementation End SHA：`46ca268316e30ed9fc438c4d178f948807419208`。
- `.venv/bin/python -m pytest -q`：**85 passed**（原 73 项 + P4 新增 12 项）。
- Python `compileall`、React TypeScript typecheck、Vite build、`cargo check`：**PASS**；坐标转换 Node tests：**2 passed**。
- `npm run desktop:dev`：Tauri 原生进程启动且 `/health` 返回 Python 3.12.14；`npm run desktop:build`：**PASS**，最终 `.app` 直接启动并在原生窗口显示 P4-X1 与设置页依赖状态。
- `git diff --check`：**PASS**。真实模型权重不在 pytest 中下载或运行。

## 真实模型与纵向 E2E

- ModelManager 正式路径安装：PP-OCRv6 Small 31,628,665 bytes、Medium、PP-FormulaNet_plus-M、Qwen3-VL 4B MLX 4bit；8B 未安装。安装清单保留各源仓库 resolved revision。
- Small ONNX 检测 + DB 后处理 + 文本裁图 + CTC 解码：合成测试页 4 个 crop 经 Desktop Recognition Lab 输出 `120`、`3456`、`A`、`<`，四个 SUCCESS 记录持久化；单个冷次 1151 ms，暖次 221–232 ms。官方 PaddleOCR `general_ocr_002.png` 示例图检测 33 框，输出非空文本，confidence 0.97304、495 ms。
- Medium 经同一 Provider 管线在相同 crop 输出 `120`，SUCCESS，首次 1406 ms；该结果只证明运行路径，不构成准确率比较。
- Formula 官方 PaddleOCR 本地模型在合成分数 crop 经模板绑定、裁图、RecognitionRun 和 UI 显示 `\\frac{1}{2}`，SUCCESS，首次 6635 ms。单图手动 smoke 还覆盖乘法表达式与上下结构；上下结构输出不准确，需后续 Benchmark 评估。
- 4B MLX 本地权重在同一 `120` crop 经完整 E2E 输出 `120`，SUCCESS，UI 显示 revision 与 2532 ms。独立五例 smoke：单数字 `7`、多位整数 `3456`、选项 `B`、符号 `>`、轻微改动 `12`；加载约 1758 ms，单例暖次 718–1060 ms，进程峰值 RSS 3,480,600,576 bytes。无 8B 测试。
- ImagePipeline 合成单页手动计时 591.3 ms（这张白底样例提示 `OVEREXPOSED`）；手机上传不等待处理完毕。
- 无 Desktop CLI 隔离 smoke：经 ModelManager 在 `/tmp` 安装 Small 后，`python -m local_service.recognition_cli --json` 对四区域合成页返回 exit 0、四个 SUCCESS 与 `120` / `3456` / `A` / `<`。
- 从真实 Small/Medium/4B RecognitionRun 导出 6 条 P0 prediction，逐条通过 `prediction.schema.json` 校验，且 `decision_status` 全部保持 `REVIEW_REQUIRED`。

## 浏览器与 P2 回归

- 浏览器模板页：创建组/页、导入参考图、四题四区域、重新打开恢复；公式页区域通过鼠标拖动重画，数据库归一化坐标随之更新。
- Recognition Lab：导入合成作业页、候选分数 0.83、人工绑定 v10、显示处理图/四个 overlay/四张 crop、执行 Small/Medium/4B/Formula、同一 crop 多模型历史、P0 JSONL 导出入口；真实识别结果经 UI 可见。
- P2 浏览器：两名合成测试学生、二维码与独立 LAN 页面、预览重拍不计页、三页即时上传、删除中间页后后续页号连续、重新上传、刷新恢复、明确 finish 后自动下一学生、第二名独立采集、Mac 显示 2/2；数据库两名 Submission 均 COMPLETED，四张最终页面为 WARNING。临时 Session 已 END，真实 iPhone Safari **未验收**。

## 验证边界与发布阻塞

- 合成图与官方示例只证明集成和运行，不代表真实学生书写识别准确率。当前不做自动判分或最终 confidence 策略。
- 打包 `.app` 的原生模型中心显示四个已安装模型并如实标注 Provider 不可用；设置页显示系统 Python 3.9.6 可启动，但 Pillow、OpenCV、ONNX Runtime、Hugging Face Hub、mlx-vlm、PaddleOCR/PaddlePaddle 均缺失。退出应用后 8765 listener 关闭。正式发布需解决 Python 与依赖打包；开发 Python 3.12 `.venv-p4` 已具备真实模型运行条件。
- 桌面 `Math Grader.app` 已替换为 P4-X1 包并从该路径重新启动，原生首页显示 `P4-X1 · 本地运行`。
- P2 保持 `READY_FOR_DEVICE_TEST`，不得凭浏览器回归升级为 PASS。

## P2 LAN URL 真机验收反馈回归（2026-09-26）

- 用户报告 iPhone 扫码地址疑似把接口名拼进 IPv4。审阅运行中的 `.app` 和仓库源码后，未在现有实现中复现该 URL；原 Desktop 地址选择器曾将 IP 与 `en0` 放在同一文本中，可能产生歧义，原 QR 内容无法从当前状态追溯确认。
- 当前 Mac 网络：`en0` active，`192.168.31.89`；默认路由 `utun6`，其 `198.18.0.1` 不符合 RFC1918；仅 `en0` 是本次可用物理 LAN IPv4。开始检查时 8766 没有活动 listener。
- 新增 Python 用例覆盖：IP 与 `en0` 分离且 URL 为 `host:port`、拒绝 `192.168.31.89.en0`、拒绝非 IPv4、排除 loopback 与未运行接口、默认路由 LAN 优先、物理 LAN 优先于 VPN、多接口排序、无可用 LAN 时明确报错。新增 Desktop 单元测试确认 QR value、显示链接和显示文字都等于 API 的同一个 `capture_url`。
- `.venv/bin/python -m pytest -q tests/test_capture_bridge.py`：**18 passed**；`.venv/bin/python -m pytest -q`：**92 passed**；`compileall`：PASS。Desktop `typecheck`、Vite build、Capture URL tests **2 passed**、coordinates tests **2 passed**；`npm run desktop:build`：PASS；`git diff --check`：PASS。
- 实际 LAN Session smoke 使用临时数据库：selected `en0 / 192.168.31.89`；listener `192.168.31.89:8766`；URL `http://192.168.31.89:8766/capture?t=<redacted>`；TCP listener check PASS；之后结束 Session，8766 listener 关闭。安装更新后的 Desktop `.app` 并启动，服务报告同一 LAN IPv4，Capture Session 为 INACTIVE。
- P2 API regression 覆盖 Session/token 哈希与失效、上传/多页、删除重排、finish 幂等与下一学生推进、HTTP 权限边界和 listener 生命周期。此前 Browser E2E 已覆盖预览重拍、多页即时上传、删除重排、finish/next student 与 Desktop 队列；本次只改网络地址和 Desktop URL 展示链路。真实 iPhone Safari 尚未验证，P2 保持 **READY_FOR_DEVICE_TEST**。

---

# P5-L1 Teacher Workflow + Auto Exam Template + Grading Vertical Slice

## 基线与版本

- Start branch：`phase/p4-x1`；Start SHA：`c4316051ce3ead739f729b969275b17b52fc75c1`（只记录需求事实的提交，不是 P5 实现）。
- Implementation branch：`phase/p5-l1`；实现提交：`d123e567946aece28f8e780e3c6ff4d91df0fd7a`；Review 页码提示修正：`6510dae56f7865c2eac9500b5b331faf14519275`。
- Python 全套：**97 passed**（此前 P0–P4 92 项 + P5 新增 5 项）。
- Python 开发环境：`.venv-p4`，Python 3.12.14；正式 `.app` Python / 模型依赖打包仍是已知发布风险，本阶段没有处理。

## 自动验证

- `.venv-p4/bin/python -m pytest -q`：**97 passed**，覆盖 P0–P4 回归及全部 P5 用例。
- `npm run build`（`desktop/`，包括 TypeScript 检查）：**PASS**。
- `cargo check`（`desktop/src-tauri/`）：**PASS**。
- `git diff --check`：**PASS**。
- P5 新增 5 项测试覆盖：四页 Student A 与 Student B Assignment 模板复用；老师 Capture finish 后原图/页面进入批改工作区且不走旧 Submission job；已有题册入口和 Formula 识别路由；无 Capture 活动时可切换老师模式、开始 Capture 后拒绝切换；教师流程 API 与原图 API。

## 真实模型验收

- 在隔离临时数据库以真实本地 Qwen3-VL 4B + PP-OCRv6 Small 执行 Student A / Student B 纵向 E2E。Student A 四页触发一次整页分析，Qwen 提出 8 题；老师确认题目/区域/答案后对 8 个答案区域执行 Small OCR，确定性规则最终保存 **8/8**。Student B 四页没有再次调用整页 Qwen 分析，复用同一 Assignment 临时模板，Small OCR 运行 8 个区域并保存 **7/8**。
- 这组数据是专门制作的合成试卷，不含真实学生作业；结果证明调用与持久化路径，不构成模型准确率 Benchmark。

## 桌面老师端浏览器 E2E

- 临时服务使用 `.venv-p4` 与本地模型，监听 `127.0.0.1:8767`；Vite 使用已允许的 `127.0.0.1:1420`。临时数据目录位于系统 `/tmp`，不会混入正式用户数据。
- 通过真实 React UI 创建测试班级、两名学生和 Assignment；上传 4 张带合成算式的作业图并完成 Student A。Workspace 直接显示 4 页原图、页码和一次性试卷分析入口。
- 在普通老师页触发真实 Qwen 整页分析，显示 4 页、共 32 个题目/答案区域/标准答案候选；在界面一次确认 Assignment 临时模板。Student A 使用 PP-OCR 开始判分；由于合成页答案框未填写，低置信度结果进入人工复核。Review 页面显示原图、页号与题号；实际人工确认其中一道测试题后，待复核数从 32 降到 31。
- Student B 上传同一份 4 页合成测试卷；Workspace 显示“已确认 · 学生共用”结构，可直接开始识别判分，没有整页分析操作。Student B 进入正常识别和人工复核路径，Assignment 模板未复制成每生重新分析。
- 页码实测发现复核队列相同题号跨页重复时原 UI 只显示题号；已调整为同时显示 `第 N 页 · 第 M 题`，build 与 UI DOM 检查通过。
- 临时服务和 Vite 已停止；合成图位于 `/tmp/math-grader-p5-ui-pages/`，没有提交 Git。未对正式 `.app` 或用户本地数据库执行操作。

## 范围与边界

- P5 的 Qwen 分析、临时模板、题目识别、确定性判分、QuestionResult、Submission score 与 Human Review 均在本地服务和普通老师 UI 中接通。
- `Recognition Lab` 保留为高级工具；老师开始普通 Assignment 后不需要进入该实验页。
- 没有使用真实学生照片；没有开始 Production Runtime Packaging，也没有进行最终 Benchmark / Confidence。
- P2 Capture Bridge regression 均通过，但真实 iPhone Safari 未验收。P2 继续保持 **READY_FOR_DEVICE_TEST**，不可据此标记 PASS。

---

# P5-L2 Production Runtime Packaging + Standalone Desktop Delivery

## 基线与版本

- Branch：`phase/p5-l2`；Start SHA：`3d102bd24ddd56d0a5ac8380cfdee721e50574c7`。
- 最后代码提交 / Runtime manifest source SHA：`00063964819738c9153794cf485e096ae7ed12af`。Runtime manifest 中 app/runtime version 为 `0.1.0`。
- 本轮开始前 Python regression：**97 passed**；完成后：**103 passed**。
- 目标：Apple Silicon `arm64`、macOS **15.0+**。最终 app 安装在 `~/Desktop/Math Grader.app`，体积约 **1.3 GB**。

## 自动化与打包验证

- `.venv-p4/bin/python -m pytest -q`：**103 passed**；`compileall -q local_service scripts`：PASS；`uv lock --check`：PASS。
- `npm run typecheck`、`npm run test:coordinates` (**2 passed**)、`npm run test:capture-url` (**2 passed**)、`npm run build`：PASS。
- `cargo check`：PASS；`cargo test --lib`：**4 passed**。
- `./scripts/build_macos_app.sh`：成功生成并安装 Release `.app`；包资源、arm64 本机架构、前端 dist 与 manifest 检查 PASS；bundle 不含 `.safetensors` 模型文件。
- `codesign --verify --deep --strict`：PASS。该包使用 ad-hoc 签名、未公证且 `hardenedRuntime=false`；验证仅覆盖本地构建签名，不代表 Developer ID 发布准备完成。
- `git diff --check`：实现提交时 PASS；文档变更另行检查。

## 包内 Runtime 与真实模型 smoke

- Installed app 服务使用的解释器为 `.app/Contents/Resources/runtime/python/bin/python3.12`，CPython **3.12.14 arm64**。从隔离数据目录、仓库外工作目录和精简环境启动成功；未依赖系统 Python、虚拟环境、`PYTHONPATH` 或开发仓库。
- Startup `/health` 报告 `bundled_runtime=true`、Python 3.12.14、arm64、版本 `0.1.0` 与 capability 状态；Capture 默认 INACTIVE。服务退出后 Tauri 管理的服务子进程结束，8765/8766 均无 listener。
- 真实包内模型 smoke 使用已有本机模型目录和合成图：ImagePipeline 成功；PP-OCRv6 Small 输出 `120`；Formula 模型输出 `\frac{1}{2}`；Qwen3-VL 4B 输出 `120`。没有下载或复制模型，模型未打入 `.app`。
- 记录的 runtime 依赖版本：Pillow 11.3.0、NumPy 2.3.5、OpenCV 4.10.0、ONNX Runtime 1.30.0、Hugging Face Hub 1.33.0、PaddlePaddle 3.3.1、PaddleOCR 3.7.0、MLX 0.32.2、mlx-vlm 0.7.3；锁文件完整解析结果以 `uv.lock` 为准。

## P5 installed app E2E 与浏览器 E2E

- 使用最终安装 `.app` 的 bundled service 和隔离临时数据执行 Student A / Student B 全链路。Student A 最终三页（包括上传三页、删除中间页、重排后补拍）；finish 后推进 Student B。Qwen 4B 对 A 只做一次整页分析，老师确认临时模板；A 用 OCR、确定性判分和人工复核完成，最终 3/3。Student B 不再整页分析、复用同一 Assignment 模板并完成 Review，最终 3/3。所有图片、班级、学生均为合成测试数据。
- Capture browser E2E：实际加载 app service 的 Capture 页面，完成预览重拍不上传、逐页即时上传、删除确认及重编号、替换页、finish 确认、自动下一学生和班级完成。
- 老师 UI E2E：用 production frontend dist 的本地 preview 与隔离 app backend，浏览器实际打开 Review 并处理队列；Workspace 显示合成 Student C 三页原图、已确认且学生共用的临时模板、3/3 成绩和完成状态。此项验证的是生产构建前端经浏览器与服务的交互。
- 原生 Tauri 窗口 / Finder 双击：**未验证**。Mac 处于锁屏状态，Computer Use 无法进行 UI 操作；再次打开已安装 app 时仍返回锁屏提示。此前直接启动 bundle executable 与 health/API 测试通过，但不能替代 Finder 双击或原生 UI 检查。

## 运行目录、数据边界与未完成 Gate

- `.app` 仅含应用代码、Capture 页面、runtime 与 dependencies；不含任何模型权重。模型保存在 `~/Library/Application Support/MathGrader/models/<model-id>/`，用户数据位于同一 MathGrader Application Support 树的 data/images/cache/logs/config 目录。
- Python service 由 Tauri 管理单实例、干净启动环境、工作目录、日志和退出回收。旧式系统 Python fallback 已移除。Runtime manifest 单独记录 Python、架构、依赖版本、build date、lockfile hash 与源码 SHA。
- 发行限制：macOS 15.0+ / arm64；本地包未公证、hardened runtime 关闭。正式 Developer ID 签名、公证和其他硬件/系统组合未验证。
- P5-L2 状态：**PARTIAL**，待 Mac 解锁后验证原生窗口及 Finder 双击启动。P2 仍为 **READY_FOR_DEVICE_TEST**，真实 iPhone Safari 尚未测试。未做真实学生照片准确率 Benchmark；未启动 P6 Benchmark / Confidence。
