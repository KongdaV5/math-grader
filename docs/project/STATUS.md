# 项目状态

## 当前状态

- 阶段：**P2 — Capture Bridge**
- 当前工作包：**P2 Capture Bridge**
- 状态：**PARTIAL**（实现和自动验证完成；浏览器 UI E2E 尚未完整验证）
- Branch：`phase/p2`
- Start SHA：`83305d6f94d144ff2261340ad91f9b565ab071ad`
- Implementation End SHA：`37887fd3df772a0440580ca384843388a2de9e71`
- P0-W1 Benchmark Foundation：**PASS，未重做**
- P1-W1 Application Foundation：**PASS，40 项回归保持通过**
- 下一 Gate：解锁 Mac 后完成剩余桌面浏览器 E2E；全部通过后为 `READY_FOR_DEVICE_TEST`，真实 iPhone Safari 验收后才可标 P2 PASS。

## P1-W1 基线

- Tauri 2 原生桌面壳，React + TypeScript 页面；
- Python 标准库本地 HTTP 服务，SQLite 读写全部经过服务；
- SQLite `user_version` migrations，包含 Class、Student、Assignment、Submission、SubmissionPage、RecognitionResult 和 jobs；
- 单一 Submission 状态机，阻止非法迁移；
- SQLite 持久顺序任务队列、后台 worker、启动恢复和失败记录；
- Recognition Gateway、Provider Registry、JSON 路由配置与 Mock Provider；
- Desktop 最小操作页：新建班级/学生/作业、选学生、创建 Submission、添加占位页或本地图片、点击“完成该生”、显示后台状态和 Mock 结果；
- 更新项目路线：P0-W1 → P1 → P2 → P3 → P4 → P5 → P6 Model Benchmark → 后续 Normalize / Grader / Confidence / Student History / Analytics / UI 完善。

## P1-W1 Definition of Done（历史验收记录）

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

## P2 Capture Bridge 已实现

- Desktop API 继续只监听 `127.0.0.1:8765`；开启 Session 后，独立 Capture HTTP listener 才绑定所选 RFC1918 LAN IPv4 的 `8766`。
- 256-bit 高熵随机 token 仅短暂返回给 Desktop 生成 QR，SQLite 只存 SHA-256；Capture 路由校验 token、Host、Origin、Fetch Metadata，不暴露管理 API。
- 手机 Safari 页面用原生 `capture="environment"` 相机入口，预览后可重拍或立即上传；支持当前学生多页、缩略图、单页删除、编号重排、刷新恢复。
- 只有确认“完成该生”后 Submission 才进入 READY / QUEUED 并推进 roster；后台 worker 与下一位手机采集并行；结束/过期/进程重启时旧 token 失效并关闭 LAN listener。
- 新增 P2 自动测试 11 项；Python 全套 **51 passed**。React typecheck/build、cargo check、Tauri dev/service health、`.app` build smoke 均通过。
- Browser E2E 已验证二维码、三张测试图片即时上传、拍页不切学生、页面刷新恢复；删除/重排、finish 后换人及浏览器可视的队列步骤因 Mac 锁屏尚未验证，因此状态保持 **PARTIAL**。

## 环境与已知限制

- 完整 P1 浏览器 Mock E2E 作为历史验收证据保留。P2 的 Capture UI 浏览器流程尚未全覆盖；Mac 锁屏后 UI 点击停止派发，需要解锁后继续。
- 当前 Tauri app 从系统 `PATH` 启动 Python 3.9+；发布环境需安装 Python。服务代码与配置已随 `.app` resources 打包。
- P2 未测试真实 iPhone Safari；在真实设备 Gate 通过前，不得声称 P2 PASS。
- 本轮不提供真实 OCR、数学判分、图像质量 AI 或模型 Benchmark。

## 下一步

1. 解锁 Mac，完成 Capture browser E2E 剩余的删除/重排、finish 确认、下一学生切换、后台 Mock queue 检查；通过后把状态改为 `READY_FOR_DEVICE_TEST`。
2. 由用户按 handoff 步骤用真实 iPhone Safari 验收；用户确认通过后再标记 P2 PASS。
3. P2 PASS 前不要启动 P3。
