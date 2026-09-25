# TASK_BOARD.md

## DONE — P0-W1 Benchmark Foundation

- Owner：Codex GPT-6 Luna
- Reviewer：DeepSeek V4.1 Flash
- Status：PASS

交付：schema、runner、metrics、failure archive、pytest、report template、docs update。

## NEXT — P0-W2 Model Benchmark

- Preferred Owner：Luna；若跨模型接入/性能调度明显复杂，可升级 Terra
- Reviewer：DeepSeek V4.1 Flash
- Status：NOT STARTED；本次工作包结束后停止，等待单独启动

内容：PP-OCRv6 Small/Medium、Qwen3-VL 4B/8B fallback、Formula 候选、真实样本、延迟/内存/准确率。

## NEXT — P0-W3 Analysis & Gate

- Owner：Luna
- Reviewer：DeepSeek V4.1 Flash
- Sol：仅当 Gate 证据冲突或重大正确性问题无法裁决时使用

输出：`BENCHMARK_REPORT.md`、推荐模型组合、Precision/Coverage、failure taxonomy、Go/No-Go。

## LATER

P1 Core Engine → P2 Capture Bridge → P3 Image Preprocess → P4 Template → P5 Crop → P6 Recognition → P7 Normalize → P8 Grader → P9 Confidence/Review → P10 Student History → P11 Analytics/Handwriting → P12 Desktop Client → P13 Continuity Camera（可选）
