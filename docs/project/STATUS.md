# STATUS.md

## 项目状态

- 阶段：**P0**
- 当前工作包：**P0-W1 Benchmark Foundation**
- 状态：**READY TO START**
- 主执行：**Codex GPT-6 Luna**
- 独立审查：**DeepSeek V4.1 Flash**
- Sol：**本阶段默认不使用**

## 已完成

- v0.2 参考手册
- 多页 Submission 工作流
- “完成该生”后才切下一学生
- iPhone → Mac Capture Bridge 方向
- 每页即时上传策略
- P0 Benchmark 为第一技术 Gate
- 模型分工和交接规则

## 当前尚未完成

- Benchmark 代码骨架
- Ground Truth schema
- Dataset manifest schema
- Prediction schema
- Benchmark runner
- Metrics
- Failure archive
- pytest
- BENCHMARK_REPORT 模板
- OCR/VLM 实测

## P0-W1 Definition of Done

必须至少具备：
1. 可扩展 Benchmark 结构
2. Ground Truth JSONL schema
3. Dataset manifest schema
4. Prediction schema
5. Answer Exact Match
6. Auto-grade Precision
7. Auto Coverage
8. Review Rate
9. False Auto-Accept
10. Failure case 可追溯
11. 最小 CLI / runner
12. 单元测试
13. 报告模板
14. 无模型硬编码
15. 状态文档已更新

下一工作包：**P0-W2 Model Benchmark**，仅在 P0-W1 PASS 后启动。
