# P1-W1 测试状态

## 基线

- Start branch：`main`
- Start SHA：`0ffc4b7ff336d33f8836fbb9f998daea5443c4fe`
- Implementation End SHA：`cd1114122396f2f8c11df3abef71d468e012abe1`
- 开始修改前 `.venv/bin/python -m pytest`：**28 passed**（P0-W1 基线）

## 环境

- Python：3.9.6
- pytest：8.4.2
- jsonschema：4.25.1
- Node：24.21.0
- Tauri JS API / CLI：2.11.1 / 2.11.5
- Rust：1.98.1（隔离安装到 `/tmp`，未改用户全局 PATH）
- Xcode：16.4

## 最终验证

- `.venv/bin/python -m pytest`：**40 passed**，包括原 P0-W1 28 项和 P1 新增 12 项；
- `.venv/bin/python -m compileall -q benchmark local_service tests`：**PASS**；
- `.venv/bin/python -m local_service --help`：**PASS**；
- `npm run typecheck`（`desktop/`）：**PASS**；
- `npm run build`（`desktop/`）：**PASS**；
- `cargo check`（`desktop/src-tauri/`）：**PASS**；
- `npm run desktop:dev`：**PASS**，Tauri 原生进程启动并拉起本地 Python 服务；
- `npm run desktop:build`：**PASS**，生成 macOS `Math Grader.app`；
- 从打包 `.app` 启动后请求 `http://127.0.0.1:8765/health`：**PASS**；
- `npm run demo:dev` 浏览器 UI：新建班级、学生、作业 → 开始 Submission → 添加占位页 → 完成该生 → UI 显示 `COMPLETED` 与 Mock Provider 结果：**PASS**；
- `git diff --check`：**PASS**；
- `npm install` audit：**0 vulnerabilities**。

## P1 新增测试覆盖

- SQLite migration / schema 初始化；Class / Student / Assignment 创建和读取；
- Student 与 Assignment 的 Class 归属校验；
- Submission 创建、多页添加、page_count、图片落盘；
- 全部合法状态迁移，以及 `EMPTY → PROCESSING` 与错误 finish 拒绝；
- finish 原子地进入 READY / QUEUED；worker 调用 Mock、持久化 RecognitionResult 并完成 Submission；
- 多 Submission FIFO 顺序处理；一个任务失败后错误被记录且后续任务继续；
- Provider route/fallback 与 Provider Registry 扩展；
- 本地 HTTP server + worker 的完整 API smoke 和状态码验证。

## 已知验证边界

- 机器屏幕在原生 app 启动时处于锁定状态，无法用 GUI 辅助功能树读取原生窗口内容；Tauri 原生进程、打包 app 和服务健康响应已验证，React UI 与服务的交互闭环在浏览器中完整验证。
- `.app` 使用系统 `python3` 启动打包的服务代码，因此运行机器需有 Python 3.9+。
- 没有真实 OCR/VLM 或真实作业数据测试；这属于 P5 / P6 后续阶段。
