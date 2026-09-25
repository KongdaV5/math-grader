# P0-W1 测试状态

## 环境

- Python：3.9.6
- pytest：8.4.2
- jsonschema：4.25.1
- 安装：项目 `.venv`，依赖未装入全局 Python 环境

## 结果

- Unit / schema / metrics / runner tests：**28 passed**
- CLI smoke test（合成单题数据，review-only stub）：**PASS**
- 手工 CLI smoke command（空示例数据集）：**PASS**；生成 `metrics.json`、预测快照、报告和空失败索引
- Python compile check：**PASS**
- `git diff --cached --check`：**PASS**（当前 P0-W1 实现差异）
- 真实 OCR/VLM Benchmark：**NOT RUN**（不属于 P0-W1）
- Regression：**NOT RUN**（当前尚无后续识别或产品模块）

## 覆盖范围

- 三种 Draft 2020-12 schema 的 meta-validation 和字段验证
- 缺字段、错误类型、非法 `answer_type`、Prediction error 必须送审
- JSONL 损坏行、非 UTF-8 输入、重复 Ground Truth `sample_id`、重复 `(sample_id, run_id)`
- Exact Match、Auto-grade Precision、Coverage、Review Rate、False Auto-Accept
- 空数据、全自动、全复核、混合、缺失预测和多 RecognitionRun 选择
- Failure Archive 的 schema error、invalid prediction、review、recognition mismatch 和 false auto-accept 路径
- 原始图片引用保持在归档记录中；不复制图片

## 数据保护

- `benchmark/dataset/raw/*` 被 `.gitignore` 忽略，仅保留 `README.md`
- `git check-ignore` 已确认照片路径和 `benchmark/runs/` 输出路径被忽略
- 当前仓库未跟踪或提交真实学生作业图片
