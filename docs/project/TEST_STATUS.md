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

---

# P2 Capture Bridge 测试状态

## 基线与版本

- Start branch：`phase/p1`
- Start SHA：`83305d6f94d144ff2261340ad91f9b565ab071ad`
- Implementation branch：`phase/p2`
- Implementation End SHA：`37887fd3df772a0440580ca384843388a2de9e71`
- Python：3.9.6；Node：24.21.0；Rust：1.98.1（Rust 工具链隔离安装于 `/tmp`）。

## 自动验证

- `.venv/bin/python -m pytest -q`：**51 passed**（P1 原 40 项 + P2 新增 11 项）；
- `.venv/bin/python -m compileall -q local_service tests`：**PASS**；
- `.venv/bin/python -m local_service --help`：**PASS**；
- `npm run typecheck`：**PASS**；`npm run build`：**PASS**；
- `cargo check`：**PASS**；`npm run desktop:dev`：**PASS**，Tauri dev 进程启动且本地服务 `/health` 返回 `ok`；
- `npm run desktop:build`：**PASS**，生成 `Math Grader.app`；Capture 手机网页已随服务资源纳入 bundle；
- `git diff --check` 与 staged diff 检查：**PASS**。

## P2 自动测试覆盖

- LAN 地址发现优先 Wi-Fi，并忽略 VPN benchmark 范围；Session token hash、失效/过期/结束/进程重启；
- 多页图片上传及 metadata、UUID 幂等、MIME/签名/空文件/大小校验、删除和 page_index 重排、磁盘安全路径；
- 当前 Submission 校验、防迟到上传串学生、跨 Submission 页面访问拒绝；
- “完成该生”前不推进；确认后进入队列且只创建一个任务；前一位 PROCESSING 时下一位 CAPTURING；最后一位完成后不循环；
- HTTP Capture 面 Host/Origin/token、路由隔离、上传/读取/删除/finish/session end；Desktop admin 非 loopback 监听拒绝；Session 过期后 Capture listener 关闭。

## Browser E2E 与验收边界

- 已完成浏览器实际操作：Desktop UI 建立测试班级、学生、作业并开启 Session；显示的 LAN 地址为 `192.168.31.89:8766`，QR 只含 token URL；手机等价页面可打开；3 张测试 PNG 在各次确认后立即上传；拍照期间没有自动换学生；刷新后 Session、当前学生和页数成功恢复。
- 未完成浏览器 UI 步骤：更新为页面内无障碍确认框后，删除/重排、确认 finish、切换下一学生、完成 Mock queue 尚未在浏览器 UI 验证。Mac 屏幕锁定后自动化点击不再向页面派发事件；这部分不能记为 PASS。
- 真实 iPhone Safari：**未测试**；照片测试使用无真实学生内容的本地 1×1 PNG fixture，fixture 保存在 `/tmp`，未提交 Git。
- 因浏览器 UI E2E 尚未完成，当前状态为 **PARTIAL**；完整浏览器 E2E 通过后方可转 `READY_FOR_DEVICE_TEST`，真实 iPhone 通过后方可将 P2 标记 PASS。

## Release 风险

- 保留 P1 已知正式发布阻塞：打包 `.app` 通过系统 `python3` 启动服务，目标 Mac 需要 PATH 中有 Python 3.9+；P2 未改运行时打包架构。
