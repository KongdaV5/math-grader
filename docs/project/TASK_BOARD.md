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

## NEXT — P2 Capture Bridge

- Status：NOT STARTED；仅在单独启动 P2 时执行。
- 前置：复用 P1 Submission 状态机和每页上传 API，设计 Capture Session、设备授权、断线恢复、多页隔离和明确的“完成该生”切换。
- Do not：不改成拍一页自动换学生；不要把图片处理、模板、真实 OCR 顺手并入 P2。

## LATER — P3 至 P6

1. P3 Image Pipeline；
2. P4 Template System；
3. P5 Recognition Integration；
4. P6 Model Benchmark（P0 Benchmark 子系统永久保留，P0-W2 不再是 P1 前置）。

其后：Normalize → Grader → Confidence / Review → Student History → Analytics → Desktop UI 完善。
