# 项目状态

## 当前状态

- 阶段：**P1 — Application Foundation**
- 当前工作包：**P1-W1 — Application Foundation**
- 状态：**PASS**
- Branch：`phase/p1`
- Start SHA：`0ffc4b7ff336d33f8836fbb9f998daea5443c4fe`
- Implementation End SHA：`cd1114122396f2f8c11df3abef71d468e012abe1`
- P0-W1 Benchmark Foundation：**PASS，未重做**
- 下一 Gate：**P2 Capture Bridge**（本轮未启动）

## P1-W1 完成内容

- Tauri 2 原生桌面壳，React + TypeScript 页面；
- Python 标准库本地 HTTP 服务，SQLite 读写全部经过服务；
- SQLite `user_version` migrations，包含 Class、Student、Assignment、Submission、SubmissionPage、RecognitionResult 和 jobs；
- 单一 Submission 状态机，阻止非法迁移；
- SQLite 持久顺序任务队列、后台 worker、启动恢复和失败记录；
- Recognition Gateway、Provider Registry、JSON 路由配置与 Mock Provider；
- Desktop 最小操作页：新建班级/学生/作业、选学生、创建 Submission、添加占位页或本地图片、点击“完成该生”、显示后台状态和 Mock 结果；
- 更新项目路线：P0-W1 → P1 → P2 → P3 → P4 → P5 → P6 Model Benchmark → 后续 Normalize / Grader / Confidence / Student History / Analytics / UI 完善。

## P1-W1 Definition of Done

1. 本地 SQLite 初始化与实体最小路径：**PASS**
2. 多页计数和 Submission 状态机：**PASS**
3. `finish` 进入后台队列，顺序 worker 处理多个 Submission：**PASS**
4. 单任务失败后 worker 继续下一项，任务/Submission 有错误记录：**PASS**
5. Mock Provider 可配置并经 Gateway 调用，结果写入 SQLite：**PASS**
6. Desktop ↔ Local Service HTTP smoke 与真实浏览器 UI 闭环：**PASS**
7. React TypeScript typecheck / build：**PASS**
8. Tauri 原生 `cargo check`、`tauri dev` 与 macOS `.app` build：**PASS**
9. 原 P0-W1 28 项测试回归：**PASS**（最终全套 40 项通过）
10. Python compile、`git diff --check`：**PASS**

## 环境与已知限制

- P1 UI 与本地服务已在本机浏览器中完成真实 Mock E2E；打包 `.app` 也已启动，包内服务 `/health` 返回正常。
- 桌面会话锁屏时无法用辅助功能树检查原生窗口内容；原生进程和包内服务均已验证运行，界面交互由同源 React 浏览器 smoke 覆盖。
- 当前 Tauri app 从系统 `PATH` 启动 Python 3.9+；发布环境需安装 Python。服务代码与配置已随 `.app` resources 打包。
- P1 不提供真实 OCR、数学判分、iPhone Capture Bridge 或模型 Benchmark。

## 下一步

P1-W1 到此结束并交接。本轮不启动 P2。P2 前置条件是保持当前服务 API、实体与状态机稳定，随后为每页 Capture Bridge 上传和学生切换流程增加会话与恢复设计。
