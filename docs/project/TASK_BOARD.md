# TASK_BOARD.md

## DONE — P0-W1 Benchmark Foundation

- Owner：Codex GPT-6 Luna
- Status：PASS
- 交付：schema、runner、metrics、failure archive、28 项 pytest、report template。
- 结果留存于 P0-W1 handoff；不要重做此工作包。

## DONE — P1-W1 Application Foundation

- Owner：Codex GPT-6 Luna
- Status：PASS
- Branch：`phase/p1`
- 交付：Tauri 2 + React + TypeScript 桌面壳；Python 本地服务；SQLite migrations；Class / Student / Assignment / 多页 Submission；集中状态机；持久队列与 worker；Recognition Gateway / Provider Registry / Mock；真实浏览器 UI ↔ 服务 Mock E2E；macOS Tauri `.app` build smoke。
- 测试：原 P0 28 项回归及 P1 12 项新测试全部通过，总计 40 项。
- 完整交接：`docs/project/handoffs/P1-W1-2026-09-25.md`。

## IN PROGRESS — P2 Capture Bridge

- Owner：Codex GPT-6 Luna
- Status：**READY_FOR_DEVICE_TEST**；实现、自动验证和桌面浏览器 UI E2E 均已通过。真实 iPhone Safari 尚未验收，P2 暂不能标记 PASS。
- Branch：`phase/p2`
- Start SHA：`83305d6f94d144ff2261340ad91f9b565ab071ad`
- Implementation End SHA：`37887fd3df772a0440580ca384843388a2de9e71`
- 交付：独立 Capture LAN 监听器、Session token/hash 与生命周期、手机 Safari 原生相机入口、每页即时上传、缩略图/删除/重排、明确 finish、班级顺序推进、二维码及 Mac 后台队列状态。
- 自动测试：51 passed（P1 40 项回归 + P2 11 项）；完整验证矩阵见 `TEST_STATUS.md`。
- Browser E2E：已验证创建临时班级/学生/作业和二维码；预览重拍不增加页数；三页即时上传、删除中间页后页码整理、刷新恢复；确认 finish 后自动换学生；第二位学生页面归属正确；Mac 显示上一位学生 `排队中`；末位完成后手机页显示全班完成，Mac 显示 2/2 和两位学生队列。
- Gate：**READY_FOR_DEVICE_TEST**。由用户使用真实 iPhone Safari 完成同 Wi-Fi、扫码、拍摄/删除/重拍、学生推进及 Mac 归属/队列验收后，才可将 P2 标记 PASS。
- P2 真实 iPhone Safari Gate 独立保留；新授权允许 P3-X1 先行开发。不要把 P2 标记 PASS。

## DONE WITH BLOCKERS — P3-X1 Product Framework & Model Runtime Foundation

- Branch：`phase/p3-x1`，从 `phase/p2` 的 `cc871a733fb942e42d3e156282596f31212312d0` 创建；不合并到 main。
- 状态：**PASS WITH BLOCKERS**；正式 Desktop Shell、模型中心/管理器、Provider 运行层、ImagePipeline、Template Domain 的联合工作包已落地。
- 验收：Small 官方 ONNX 文件组真实安装/验证/ONNX 加载/删除；73 项 Python 测试；浏览器九页、模板/模型中心和 P2 Capture 回归；Tauri dev/build/原生 app 启动。
- Blockers：OCR 真正的检测+识别后处理、Formula 本地推理、MLX 大模型运行未完成；正式 `.app` 仍依赖系统 Python 3.9+ 及另行安装 Python 依赖。
- 不做真实模型准确率 Benchmark、最终判分、完整人工复核或云服务。

## DONE — P4-X1 Template → Crop → Real Recognition → Result Inspection

- Branch：`phase/p4-x1`，从 `fa9564d5a5ad47f6dffcd52914d0546f18e41589` 创建；未合并 main。
- Implementation End SHA：`46ca268316e30ed9fc438c4d178f948807419208`。
- 状态：**PASS**；手机上传异步 Image Job、模板编辑/版本快照、候选匹配、裁图、真实识别路由与历史、Recognition Lab 和 P0 prediction adapter 均形成可检查的纵向链路。
- 真实运行：PP-OCRv6 Small/Medium、PP-FormulaNet_plus-M、Qwen3-VL 4B MLX 4bit 均通过本地安装及推理。8B 未安装，尚无真实学生照片 Benchmark 或最终模型排名。
- 验证：Python **85 passed**、前端坐标 **2 passed**、TypeScript/Vite、cargo check、Tauri dev/build/打包 app 启动及 P2 浏览器回归均通过。
- Release blocker：正式 `.app` 使用系统 Python 与未随包提供的 OCR/Formula/MLX 依赖；运行环境页已明确显示。P2 仍为 `READY_FOR_DEVICE_TEST`。
- 完整交接：`docs/project/handoffs/P4-X1-2026-09-26.md`。

## DONE — P5-L1 Teacher Workflow + Auto Exam Template + Grading Vertical Slice

- Model request：GPT-6 Luna。当前线程不提供模型切换能力；未使用 Sol，也未委派其他模型。
- Branch：`phase/p5-l1`。
- Start SHA：`c4316051ce3ead739f729b969275b17b52fc75c1`；这是需求记录提交，不是 P5 实现。
- 状态：**PASS**；P5-L1 实现、真实模型隔离 E2E、桌面浏览器老师流程和 P0–P4 regression 已完成。
- Implementation End SHA：`6510dae56f7865c2eac9500b5b331faf14519275`。
- 明确排除：Production Runtime Packaging、最终 Benchmark / Confidence。

User-defined end-to-end target:

`手机拍摄多页 → Mac 即时看到该生全部页面 → 无现成模板时选择“自动分析本次试卷” → AI 提取题目/分题/答案区域并提出标准答案 → 老师一次确认 → 为本次测验生成临时模板 → 按该结构识别学生答案 → 确定性判分 → 人工复核 → 得出成绩 → 下一名学生复用同一试卷结构`

- One teacher confirmation should commit the exam structure for the current assignment; later students in that assignment reuse that structure without repeating setup.
- AI analysis proposes structure and answers for teacher confirmation. Grading uses explicit deterministic answer rules; uncertain or unsupported answers remain in human review.
- The temporary template is scoped to the current quiz/assignment. Whether to promote it into the reusable template library is a separate future decision.
- P5 delivers the teacher-facing Submission Workspace, existing-workbook/new-exam entry, one-time Qwen3-VL 4B full-page analysis, editable Answer Key Builder, Assignment-scoped temporary template, normal PP-OCR/Formula/Qwen answer recognition, deterministic grading, human review, and final QuestionResult/Submission score.
- Acceptance includes a four-page Student A flow, Student B reuse without another full-page exam analysis, P0–P4 regression, and a handoff. P2's real iPhone Safari gate remains independent and is still `READY_FOR_DEVICE_TEST`.
- 真实本地 Qwen3-VL 4B + PP-OCRv6 Small 隔离数据验收：Student A 四页一次试卷分析、8 题 8/8；Student B 复用 Assignment 模板、不重复整页分析、7/8。桌面 UI 另外验证四页图像可见、分析草稿与一次确认、Student B 模板复用、人工复核单题确认。测试图片为合成内容。
- 验证：Python **97 passed**；React TypeScript/Vite build、`cargo check`、`git diff --check` 通过。完整记录：`TEST_STATUS.md`、`docs/project/handoffs/P5-L1-2026-09-26.md`。
- 明确未开始：Production Runtime Packaging、最终 Benchmark / Confidence；P2 仍是 `READY_FOR_DEVICE_TEST`。
- 完整交接：`docs/project/handoffs/P5-L1-2026-09-26.md`。

## PARTIAL — P5-L2 Production Runtime Packaging + Standalone Desktop Delivery

- Model request：GPT-6 Luna；本轮未使用 Sol，未委派其他模型进行实现或审查。
- Branch：`phase/p5-l2`；Start SHA：`3d102bd24ddd56d0a5ac8380cfdee721e50574c7`。
- Code implementation End SHA：`00063964819738c9153794cf485e096ae7ed12af`；后续文档提交与代码实现分开。
- 状态：**PARTIAL**。Production `.app` 已构建并安装至 `~/Desktop/Math Grader.app`；包内 Python/runtime、模型推理、后端 P5 E2E、生产前端浏览器流程和 P2 Capture 浏览器回归已验证。Mac 锁屏导致原生窗口检查及 Finder 双击验收无法完成。
- 交付：CPython 3.12.14 arm64 与锁定依赖随 `.app`，Release 不回退至系统 Python；服务由 Tauri 管理生命周期、日志和单实例；用户模型独立留在 `~/Library/Application Support/MathGrader/models/`。`.app` 约 1.3 GB、ad-hoc 签名并验证、未公证；当前目标 macOS 15.0+ arm64。
- 验证：Python **103 passed**；compileall、uv lock check、React typecheck/build、前端坐标和 Capture URL tests、cargo check/4 Rust 单元测试、release `.app` 构建/架构与资源检查/codesign、包内四种真实模型烟雾测试、Installed app 双学生 P5 E2E 和 Capture/老师端浏览器 E2E 均通过。细节见 `TEST_STATUS.md` 和 P5-L2 handoff。
- 未开始最终 Benchmark / Confidence；未使用真实学生照片；未打包模型权重；P2 仍保持 **READY_FOR_DEVICE_TEST**，未完成真实 iPhone Safari 验收。
- 完整交接：`docs/project/handoffs/P5-L2-2026-09-26.md`。

## LATER — P5-L2 之后

先补完 P5-L2 原生桌面/Finder 启动验收，再按独立 handoff 完成 P2 真实 iPhone Safari Gate。P6 Model Benchmark、Confidence / Human Review 深化、Student History 和 Analytics 均未启动，需要后续明确授权。

P0 Benchmark 子系统永久保留；P0-W2 不再是 P1 前置。
