# P0-W1 — Codex GPT-6 Luna 正式开工指令

你正在继续 **Math Grader / 本地小学数学作业拍照批改系统** 项目。

## 0. 角色

你是本工作包唯一代码 Writer。默认使用 GPT-6 Luna 完成。**不要升级到 Sol**。若遇到真正无法可靠解决的关键架构/正确性阻塞，只在交接中标记“建议升级”，不要自行改用 Sol。

## 1. 开始前必须阅读

按顺序阅读：
1. `docs/project/REFERENCE.md`
2. `docs/project/DECISIONS.md`
3. `docs/project/STATUS.md`
4. `docs/project/TEST_STATUS.md`
5. `docs/project/TASK_BOARD.md`
6. `docs/project/HANDOFF_LATEST.md`

然后核对当前 Git branch、HEAD SHA、工作树是否干净。以仓库事实源为准，不从聊天记忆猜状态。

## 2. 当前唯一任务

**P0-W1 Benchmark Foundation**

目标：建立后续真实 OCR/VLM Benchmark 的统一基础设施和指标体系。本轮不是模型能力评测本身，也不是正式产品开发。

## 3. 必须完成

### A. Benchmark 数据协议
支持 dataset manifest、ground truth JSONL、predictions、failures、reports。不得把具体模型路径硬编码进 schema。

### B. Ground Truth schema
至少支持：
- sample_id
- image / image_ref
- student_id（允许匿名）
- page_id
- question_id
- answer_type
- student_answer_gt
- correct_answer
- has_correction
- image_quality
- metadata

要求：required/optional 明确；answer_type 受控验证；schema 可版本化。

### C. Prediction schema
至少支持：
- sample_id
- model_name
- model_version
- raw_prediction
- normalized_prediction
- model_confidence
- decision_status
- decision_confidence
- latency_ms
- error

必须允许同一题保存 OCR、4B、8B 等多轮 RecognitionRun，而不是只能存一个最终结果。

### D. Metrics
必须实现并单测：
1. Answer Exact Match
2. Auto-grade Precision
3. Auto Coverage
4. Review Rate
5. False Auto-Accept

分母为 0 时必须有明确行为，禁止 NaN/Infinity 泄漏。

### E. Runner / CLI
提供最小可运行入口，例如：
`python -m benchmark.run --dataset ...`

能够读取 Ground Truth、接受 prediction adapter、计算 metrics、输出结构化结果和基础报告数据。本轮允许 stub/mock predictor，不要提前接所有真实模型。

### F. Failure archive
至少按 recognition_mismatch、false_auto_accept、review_required、invalid_prediction、schema_error 归档/索引。不要复制覆盖用户原始图片，优先保存引用和 ID。

### G. Tests
至少覆盖 schema validation、metrics、malformed JSONL、duplicate sample_id、empty dataset、missing prediction、full-auto、full-review、mixed、false auto-accept。

### H. Report Template
生成 `benchmark/reports/BENCHMARK_REPORT_TEMPLATE.md`，至少包含 dataset summary、model/config、exact match、precision、coverage、review rate、false auto-accept、latency、memory placeholder、failure taxonomy、decision section。

## 4. 明确禁止

不要开发完整桌面 UI、Capture Bridge、学生管理、正式模板系统；不要开始 P0-W2；不要下载所有 OCR/VLM；不要让 Qwen27B 成为产品依赖；不要使用 Sol；不要大规模重写 REFERENCE；不要为未来功能过度抽象；不要为测试通过硬编码答案。

## 5. 工程要求

- Python/依赖版本明确
- 新依赖最小
- 核心指标易测试
- 输入错误显式报错
- sample_id 全程可追踪
- 结果可重复
- 不静默吞异常

## 6. Git 与验证

开发中使用 scoped tests。完成后至少执行：单元测试、schema tests、metrics tests、runner smoke test、`git diff --check`。如果已有 lint/typecheck，执行相关 scoped checks。

## 7. 完成后必须更新

1. `docs/project/STATUS.md`
2. `docs/project/TEST_STATUS.md`
3. 新建 `docs/project/handoffs/P0-W1-<date>.md`
4. 更新 `docs/project/HANDOFF_LATEST.md`

交接必须包含 Start SHA、End SHA、Branch、修改文件、测试命令/结果、已知问题、“不要重做”的内容、下一任务建议。

## 8. 最终输出

只给：
1. 状态：PASS / PARTIAL / BLOCKED
2. Start SHA
3. End SHA
4. 修改文件概览
5. 测试结果
6. 已知问题
7. 是否满足 P0-W1 Definition of Done
8. 下一步建议

**不要开始 P0-W2。**
