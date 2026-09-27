> 项目知识入口已于2026-09-26收敛到 [Obsidian canonical Status.md](</Users/kongda/Documents/Obsidian/obsidian-vault/Projects/Math-Grader/Status.md>)。以下原文保留为历史/clone技术参考，不再独立更新当前项目状态；其中PASS仅对应原阶段证据。

# 项目状态

## 当前状态

- 阶段：**P5-L2 — Production Runtime Packaging + Standalone Desktop Delivery**
- 当前工作包：**P5-L2**
- 状态：**PASS**（最终 Native Gate 已验证原生图片与大图预览、P5 Teacher Workflow / Human Review / 成绩、bundled Runtime、服务生命周期与冷启动）
- Branch：`phase/p5-l2`
- Start SHA：`3d102bd24ddd56d0a5ac8380cfdee721e50574c7`
- P5-L2 Code Implementation End SHA：`295dfede7530bb7986ade6f01008d038535bf6f8`
- P5-L1：**PASS**；交付基线见 TASK_BOARD 与 P5-L1 handoff。
- P0-W1 Benchmark Foundation：**PASS，未重做**
- P1-W1 Application Foundation：**PASS**
- P2 Capture Bridge：**READY_FOR_DEVICE_TEST**；真实 iPhone Safari 尚未验收，不能标记 PASS。P2 设备验收 Gate 独立保留，当前分支未将 P2 合并到 main。
- P3-X1 Implementation End SHA：`06cd1e3035e2b870ea208efd080f68810e6929b6`
- P2 真实 iPhone Safari 设备验收独立保留；P5-L2 未启动 P6 Benchmark / Confidence。

## P1-W1 基线

- Tauri 2 原生桌面壳，React + TypeScript 页面；
- Python 标准库本地 HTTP 服务，SQLite 读写全部经过服务；
- SQLite `user_version` migrations，包含 Class、Student、Assignment、Submission、SubmissionPage、RecognitionResult 和 jobs；
- 单一 Submission 状态机，阻止非法迁移；
- SQLite 持久顺序任务队列、后台 worker、启动恢复和失败记录；
- Recognition Gateway、Provider Registry、JSON 路由配置与 Mock Provider；
- Desktop 最小操作页：新建班级/学生/作业、选学生、创建 Submission、添加占位页或本地图片、点击“完成该生”、显示后台状态和 Mock 结果；
- 更新项目路线：P0-W1 → P1 → P2 → P3 → P4 → P5 → P6 Model Benchmark → 后续 Normalize / Grader / Confidence / Student History / Analytics / UI 完善。

## P1-W1 Definition of Done（历史验收记录）

1. 本地 SQLite 初始化与实体最小路径：**PASS**
2. 多页计数和 Submission 状态机：**PASS**
3. `finish` 进入后台队列，顺序 worker 处理多个 Submission：**PASS**
4. 单任务失败后 worker 继续下一项，任务/Submission 有错误记录：**PASS**
5. Mock Provider 可配置并经 Gateway 调用，结果写入 SQLite：**PASS**
6. Desktop ↔ Local Service HTTP smoke 与真实浏览器 UI 闭环：**PASS**
7. React TypeScript typecheck / build：**PASS**
8. Tauri 原生 `cargo check`、`tauri dev` 与 macOS `.app` build：**PASS**
9. 原 P0-W1 28 项测试回归：**PASS**（最终全套 40 项通过）
10. Python compile、`git diff --check`：**PASS**

## P2 Capture Bridge 已实现

- Desktop API 继续只监听 `127.0.0.1:8765`；开启 Session 后，独立 Capture HTTP listener 才绑定所选 RFC1918 LAN IPv4 的 `8766`。
- 256-bit 高熵随机 token 仅短暂返回给 Desktop 生成 QR，SQLite 只存 SHA-256；Capture 路由校验 token、Host、Origin、Fetch Metadata，不暴露管理 API。
- 手机 Safari 页面用原生 `capture="environment"` 相机入口，预览后可重拍或立即上传；支持当前学生多页、缩略图、单页删除、编号重排、刷新恢复。
- 只有确认“完成该生”后 Submission 才进入 READY / QUEUED 并推进 roster；后台 worker 与下一位手机采集并行；结束/过期/进程重启时旧 token 失效并关闭 LAN listener。
- 新增 P2 自动测试 11 项；Python 全套 **51 passed**。React typecheck/build、cargo check、Tauri dev/service health、`.app` build smoke 均通过。
- Browser E2E 已验证二维码、预览重拍、三页即时上传、中间页删除后的页码整理、刷新恢复、明确 finish 后换学生、下一学生页面归属、Mac 队列显示和全班完成状态。临时测试 worker 保持停止以观察 `排队中`；真实设备 Gate 仍待完成。
- 2026-09-26 真机验收反馈报告 QR/地址疑似包含 `.en0`。复核当前 app bundle 未能复现：发现层和 URL formatter 均未拼接接口名；原 Desktop 地址选择项显示 `IP · interface` 容易混淆，现改为只显示 IP，并用 IPv4-only formatter 拒绝带接口名的 host。Mac 实测选中 `en0 / 192.168.31.89`，默认路由为非 LAN 候选 `utun6`；隔离数据 Session 实际绑定 `192.168.31.89:8766`，生成 URL 格式正确并已结束。新增多接口、VPN 优先级、活动接口、loopback、无 LAN 和 QR/Desktop 一致性测试；全套 Python **92 passed**。新 `.app` 已安装并启动。**P2 仍为 READY_FOR_DEVICE_TEST，未标 PASS。**

## 环境与已知限制

- 完整 P1 浏览器 Mock E2E 作为历史验收证据保留。P2 桌面浏览器 Capture UI 流程已覆盖；真实 iPhone Safari 尚未测试。
- P5-L2 已将 CPython 3.12.14 与锁定依赖放入 `.app`，Release 使用包内明确路径且没有系统 Python fallback；此项取代 P1–P4 的历史运行方式。
- 当前目标为 Apple Silicon arm64、macOS 15.0+。原生 Tauri 窗口已通过 Launchpad / LaunchServices 验收；本地 `.app` 使用 ad-hoc 签名、未公证，Finder 双击单独流程未复验，因此公开分发的 Gatekeeper / Developer ID Gate 仍未完成。
- P2 未测试真实 iPhone Safari；在真实设备 Gate 通过前，不得声称 P2 PASS。
- P2 历史交付不含真实 OCR、数学判分或模型 Benchmark；P3-X1 的真实模型边界见下节。

## P3-X1 交付结果

- 九页 Desktop Shell 已在浏览器、Tauri dev 与打包 `.app` 原生窗口中运行；原 P2 Capture Bridge 保持独立 listener 与原路由。
- macOS 新运行数据使用 `~/Library/Application Support/MathGrader/`；旧数据原位回退，不自动搬迁。模板新增 SQLite migration `003_templates.sql`。
- 五项数据驱动候选模型已进入 Model Catalog；Small 官方 ONNX 双模型完成真实下载、验证、加载、删除，未下载 4B/8B。
- 图像处理对合成样例和 PaddleOCR 官方示例图输出 processed 副本；模板的组、页面、题目、归一化答案区域已通过服务与 UI 基础操作。
- Python 全套 **73 passed**（P0/P1/P2 原 51 项 + P3-X1 新 22 项）；TypeScript、Vite、cargo check、Tauri dev/build/app startup 与浏览器回归均通过。
- 真实 PP-OCR 检测后处理/识别拼接未接入；Formula 仍是安装/依赖/错误边界；MLX 未下载大权重且未实测推理。当前 Submission 默认仍走 Mock，不能声称真实识别准确率。

## P4-X1 交付结果

- 手机上传原图快速落盘，独立 Image Job 后台运行 ImagePipeline；SubmissionPage 保存 PENDING / PROCESSING / READY / WARNING / FAILED 与质量、变换信息。
- 模板编辑器支持参考图、题目字段、受控答案类型、多个归一化答案区域、拖框/重画/删除及版本快照；候选匹配仅供人工选择，低分返回 `NO_CONFIDENT_TEMPLATE_MATCH`。
- 模板绑定后从 processed page 生成带坐标、题号、region_index 和版本的持久裁图；每次真实模型识别写入独立 RecognitionRun，历史保留并可导出 P0 prediction JSONL。
- PP-OCRv6 Small 和 Medium 使用同一完整 ONNX 检测、DB 后处理、裁图、CTC 字典解码管线；Formula 使用本地 PaddleOCR 官方模型；Qwen3-VL 4B 使用本地 MLX 权重。上述四种候选均有实际推理记录，尚无真实学生数据 Benchmark 或最终模型排名。
- Recognition Lab 位于设置的高级工具；Settings 显示依赖健康；Model Center 区分安装与 Provider 可用/已加载。
- P2 浏览器拍摄回归完成，真实 iPhone Safari 尚未验收，**P2 仍为 READY_FOR_DEVICE_TEST**。

## P5-L1 交付结果

- 普通“开始批改”页提供 Submission Workspace：Assignment → Student → Submission → Pages；手机或桌面完成提交后，可直接查看每页原图并进入批改，不需要打开 Recognition Lab。
- 老师可选模板库已有题册，或对本次多页作业执行 Qwen3-VL 4B 整页分析；系统给出题目结构、答案区域和标准答案候选，老师可编辑后一次确认。
- 确认后生成仅归属当前 Assignment 的临时模板。该 Assignment 后续学生复用结构，不再触发整页试卷分析。
- 普通批改路径使用现有 PP-OCR / Formula / Qwen 识别路由，经过确定性答案规则判分；低置信度、缺答案键或页题不匹配进入 Review。QuestionResult 与 Submission 分数在审核闭环完成后持久化。
- 实际 Qwen3-VL 4B + PP-OCRv6 Small 的隔离数据 E2E：Student A 四页分析一次并确认 8 题，8/8 完成；Student B 四页复用同一 Assignment 模板，无二次整页分析，7/8 完成。另以桌面浏览器操作真实老师端：四页原图显示、32 个题目候选编辑/确认、Student A 进入待复核、Student B 直接复用模板并进入批改，Review 页面可人工处理单题。以上均为合成测试图，无真实学生数据。
- P0–P4 回归及新增 P5 用例合计 **97 passed**；React TypeScript/Vite build、`cargo check`、`git diff --check` 通过。详细记录见 `TEST_STATUS.md` 与 P5-L1 handoff。
- P2 仍为 **READY_FOR_DEVICE_TEST**，未因 P5 回归改为 PASS。P5-L1 完成时，正式 Python/依赖打包仍是发布风险；该风险由后续 P5-L2 处理。

## P5-L2 Production Runtime Packaging 交付结果

- 分支：`phase/p5-l2`；Start SHA：`3d102bd24ddd56d0a5ac8380cfdee721e50574c7`；最终 Native Gate 代码提交及 runtime manifest SHA：`295dfede7530bb7986ade6f01008d038535bf6f8`。最新安装位置：`/Applications/Math Grader.app`；App/Runtime `0.1.0`。
- `.app` 内含 relocatable CPython **3.12.14 arm64**、锁定的 Python 运行依赖和本地服务资源；系统/用户 Python fallback 已移除。Tauri 管理单实例和服务子进程退出，日志放在 Application Support；模型仍放在用户目录，不包含在 app 内。
- Runtime 依赖锁在 `uv.lock`。本轮实际 bundle 版本包括 Pillow 11.3.0、NumPy 2.3.5、OpenCV 4.10.0、ONNX Runtime 1.30.0、Hugging Face Hub 1.33.0、PaddlePaddle 3.3.1、PaddleOCR 3.7.0、MLX 0.32.2、mlx-vlm 0.7.3。
- 真实模型包内解释器 smoke：ImagePipeline、PP-OCRv6 Small、FormulaNet、Qwen3-VL 4B 均成功处理合成 fixture；没有下载、复制或打包模型权重。Installed app 的真实 P5 backend E2E 覆盖 Student A 最终三页（含删除、重排与补拍）、Student B 模板复用、分析一次、OCR、确定性评分、Review、最终 QuestionResult/Submission score。
- 首次原生验收曾发现 `img-src` 不允许 `http://127.0.0.1:8765`，且正式库没有 Teacher Workflow 样本；两项 blocker 后续均在本机修复和补验。精确 loopback origin 已进入生产 CSP，没有 wildcard、通用 `http:` 或 Capture LAN 源。最终 Tauri WebView 四页图片、应用内原图预览、Human Review 图片都真实渲染。
- 隔离 synthetic fixture 完成 Student A 4 页 Review/最终评分 `4/8` 与 Student B 4 页模板复用/`8/8`；原生普通老师入口可选择已有题册或显示新试卷分析。Seeder 明确使用 `inference_performed=false` 的测试 provider；没有把 fixture 当成模型推理或准确率证据。测试后 fixture 已清理。
- Tauri 自动启动 bundled Python；8765 loopback 正常监听、未开启 Capture 时 8766 不监听；Cmd-Q 后 app/service 与两端口均消失。冷启动恢复隔离数据和页面；无 Terminal / 系统 Python / 手工模型服务依赖。
- 最终 bundle：CPython `3.12.14 arm64`，OpenCV/ONNX Runtime/Paddle/PaddleOCR/MLX/mlx-vlm 可用，模型权重 0；`codesign --verify --deep --strict` 通过。本地 ad-hoc 签名，未公证。
- Python 全量 **108 passed**；`compileall`、`uv lock --check`、React/TypeScript/Vite build、前端坐标/Capture URL 测试、arm64 Tauri release build、bundle CSP/metadata verification、签名、原生 Native Gate 均通过。最终 Native Gate 记录见 P5-L2 handoff。
- `.app` 约 **1.3 GB**，本地 ad-hoc codesign 验证通过，未公证，hardened runtime 关闭。最低系统版本记录为 macOS **15.0**；Intel Mac 不在当前构建目标内。
- P2 仍为 **READY_FOR_DEVICE_TEST**，真实 iPhone Safari 未测。没有进行真实学生作业准确率 Benchmark，也未开始 P6 Benchmark / Confidence。

## 下一步

1. P5-L2 Native Gate 已 PASS；P2 真实 iPhone Safari 验收仍按独立 handoff 进行，通过前保持 `READY_FOR_DEVICE_TEST`。
2. 不自动开始 P6 Benchmark / Confidence；真实学生作业准确率 Benchmark 尚未进行。
