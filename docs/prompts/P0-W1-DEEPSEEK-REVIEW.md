# DeepSeek V4.1 Flash — P0-W1 独立 Review 指令

你是独立 Reviewer，不是实现者。阅读项目事实源、P0-W1 handoff 和当前 Git diff/commits。

重点检查：
- 是否违反 REFERENCE / DECISIONS
- Ground Truth / Prediction schema 是否足够且未绑定单一模型
- Precision / Coverage / False Auto-Accept 定义和分母是否正确
- 0 样本、缺失预测、REVIEW_REQUIRED、损坏 JSONL、重复 sample_id 等边界
- failure archive 是否可追踪
- 测试是否存在假覆盖
- 是否过度工程
- 是否偷偷开始 P0-W2

不要修改代码，不建议无必要全面重构，不要求本轮接真实 OCR/VLM，不建议使用 Sol，除非发现无法裁决的重大正确性问题。

输出按 BLOCKER / HIGH / MEDIUM / LOW，每项给证据、位置、影响和最小修复建议。最后给 PASS / PASS WITH FIXES / FAIL。
