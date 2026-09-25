# START HERE — Math Grader 项目启动说明

## 当前阶段

**P0-W1 Benchmark Foundation 已完成并通过本地 Gate。**

下一工作包是 P0-W2 Model Benchmark；它尚未开始。本次交接结束后停止，不自动进入 P0-W2。不要开始完整桌面客户端、Capture Bridge、学生数据库完整实现、模板管理 UI、学习趋势 UI 或生产打包。

## 开工顺序

1. 阅读 `docs/project/REFERENCE.md`
2. 阅读 `docs/project/DECISIONS.md`
3. 阅读 `docs/project/STATUS.md`
4. 阅读 `docs/project/TEST_STATUS.md`
5. 阅读 `docs/project/HANDOFF_LATEST.md`
6. 使用 `docs/prompts/P0-W1-LUNA.md` 作为 Codex Luna 正式任务指令
7. P0-W1 完成后更新状态文档和交接文件
8. 独立审查优先使用 DeepSeek V4.1 Flash；Sol 暂不使用

## 模型资源原则

- **Codex GPT-6 Luna：默认主力**
- Codex GPT-6 Terra：复杂跨模块工作包
- Codex GPT-6 Sol：默认禁用；仅关键架构歧义、重大正确性边界、长期无法定位的系统性问题或最终关键 Gate
- DeepSeek V4.1 Flash：独立 Reviewer
- 混元4：备用实施者，适合边界清晰的独立模块
- 本地 Qwen3.8 27B IQ3：不限量杂活、日志、测试数据、简单预审

## 关键纪律

- 同一时间只有一个代码 Writer
- Reviewer 默认不直接修改代码
- 已 PASS 的工作不要重复实现
- 小修只跑 scoped tests
- 工作包完成跑模块回归
- 阶段 Gate 才跑 full regression
