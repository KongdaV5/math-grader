# TEST_STATUS.md

## 当前状态

尚未开始代码级测试。

## P0-W1 预期测试

- Schema：合法/缺字段/非法 answer_type/错误类型
- Metrics：Exact Match、Precision、Coverage、Review Rate、False Auto-Accept
- 边界：0 样本、全自动、全复核、混合、缺失预测
- Runner：空目录、损坏 JSONL、重复 sample_id、缺失 prediction
- Failure Archive：可追溯 sample_id/question_id，不覆盖原始图片

## 当前结果

- Unit tests：NOT RUN
- Integration tests：NOT RUN
- Benchmark：NOT RUN
- Regression：NOT RUN
