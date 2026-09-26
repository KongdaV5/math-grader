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
- Status：**PARTIAL**；实现已提交，Python、React、Rust 与 Tauri 检查通过；完整浏览器 UI E2E 仍需在 Mac 解锁后补验。
- Branch：`phase/p2`
- Start SHA：`83305d6f94d144ff2261340ad91f9b565ab071ad`
- Implementation End SHA：`37887fd3df772a0440580ca384843388a2de9e71`
- 交付：独立 Capture LAN 监听器、Session token/hash 与生命周期、手机 Safari 原生相机入口、每页即时上传、缩略图/删除/重排、明确 finish、班级顺序推进、二维码及 Mac 后台队列状态。
- 自动测试：51 passed（P1 40 项回归 + P2 11 项）；完整验证矩阵见 `TEST_STATUS.md`。
- Browser E2E：已验证 Mac UI 建立样例班级/作业、生成真实二维码、手机等价页面即时上传 3 张测试图片、拍页不切换学生、刷新恢复。锁屏前未验证删除确认、finish 换学生和后台队列 UI；不得将其标为通过。
- Gate：Mac 解锁后完成剩余桌面浏览器 E2E，全部通过后转 `READY_FOR_DEVICE_TEST`；真实 iPhone Safari 验收完成前 P2 不得标记 PASS。
- Do not：不开发 OCR/VLM、图像处理、模板、判分、Continuity Camera、iOS 原生 App，也不开始 P3。

## LATER — P3 至 P6

1. P3 Image Pipeline；
2. P4 Template System；
3. P5 Recognition Integration；
4. P6 Model Benchmark（P0 Benchmark 子系统永久保留，P0-W2 不再是 P1 前置）。

其后：Normalize → Grader → Confidence / Review → Student History → Analytics → Desktop UI 完善。
