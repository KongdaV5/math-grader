# 项目状态

## 当前状态

- 阶段：**P4-X1 — Template → Crop → Real Recognition → Result Inspection**
- 当前工作包：**P4-X1**
- 状态：**PASS**（真实 Small、Medium、Formula、4B 模型链路及客户端检查已通过；正式 Python/依赖打包仍是发布阻塞）
- Branch：`phase/p4-x1`
- Start SHA：`fa9564d5a5ad47f6dffcd52914d0546f18e41589`
- P4-X1 Implementation End SHA：`46ca268316e30ed9fc438c4d178f948807419208`
- P0-W1 Benchmark Foundation：**PASS，未重做**
- P1-W1 Application Foundation：**PASS**
- P2 Capture Bridge：**READY_FOR_DEVICE_TEST**；真实 iPhone Safari 尚未验收，不能标记 PASS。本轮按新授权启动 P3-X1，未合并 P2 到 main。
- P3-X1 Implementation End SHA：`06cd1e3035e2b870ea208efd080f68810e6929b6`
- 下一 Gate：P2 真实 iPhone Safari 设备验收独立保留；P4 完成后停止，不自动开始判分。

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
- Browser E2E 已验证二维码、预览重拍、三页即时上传、中间页删除后的页码整理、刷新恢复、明确 finish 后换学生、下一学生页面归属、Mac 队列显示和全班完成状态。临时测试 worker 保持停止以观察 `排队中`；真实设备 Gate 仍待完成。
- 2026-09-26 真机验收反馈报告 QR/地址疑似包含 `.en0`。复核当前 app bundle 未能复现：发现层和 URL formatter 均未拼接接口名；原 Desktop 地址选择项显示 `IP · interface` 容易混淆，现改为只显示 IP，并用 IPv4-only formatter 拒绝带接口名的 host。Mac 实测选中 `en0 / 192.168.31.89`，默认路由为非 LAN 候选 `utun6`；隔离数据 Session 实际绑定 `192.168.31.89:8766`，生成 URL 格式正确并已结束。新增多接口、VPN 优先级、活动接口、loopback、无 LAN 和 QR/Desktop 一致性测试；全套 Python **92 passed**。新 `.app` 已安装并启动。**P2 仍为 READY_FOR_DEVICE_TEST，未标 PASS。**

## 环境与已知限制

- 完整 P1 浏览器 Mock E2E 作为历史验收证据保留。P2 桌面浏览器 Capture UI 流程已覆盖；真实 iPhone Safari 尚未测试。
- 当前 Tauri app 从系统 `PATH` 启动 Python 3.9+；发布环境需安装 Python。服务代码与配置已随 `.app` resources 打包。
- P2 未测试真实 iPhone Safari；在真实设备 Gate 通过前，不得声称 P2 PASS。
- P2 历史交付不含真实 OCR、数学判分或模型 Benchmark；P3-X1 的真实模型边界见下节。

## P3-X1 交付结果

- 九页 Desktop Shell 已在浏览器、Tauri dev 与打包 `.app` 原生窗口中运行；原 P2 Capture Bridge 保持独立 listener 与原路由。
- macOS 新运行数据使用 `~/Library/Application Support/MathGrader/`；旧数据原位回退，不自动搬迁。模板新增 SQLite migration `003_templates.sql`。
- 五项数据驱动候选模型已进入 Model Catalog；Small 官方 ONNX 双模型完成真实下载、验证、加载、删除，未下载 4B/8B。
- 图像处理对合成样例和 PaddleOCR 官方示例图输出 processed 副本；模板的组、页面、题目、归一化答案区域已通过服务与 UI 基础操作。
- Python 全套 **73 passed**（P0/P1/P2 原 51 项 + P3-X1 新 22 项）；TypeScript、Vite、cargo check、Tauri dev/build/app startup 与浏览器回归均通过。
- 真实 PP-OCR 检测后处理/识别拼接未接入；Formula 仍是安装/依赖/错误边界；MLX 未下载大权重且未实测推理。当前 Submission 默认仍走 Mock，不能声称真实识别准确率。

## P4-X1 交付结果

- 手机上传原图快速落盘，独立 Image Job 后台运行 ImagePipeline；SubmissionPage 保存 PENDING / PROCESSING / READY / WARNING / FAILED 与质量、变换信息。
- 模板编辑器支持参考图、题目字段、受控答案类型、多个归一化答案区域、拖框/重画/删除及版本快照；候选匹配仅供人工选择，低分返回 `NO_CONFIDENT_TEMPLATE_MATCH`。
- 模板绑定后从 processed page 生成带坐标、题号、region_index 和版本的持久裁图；每次真实模型识别写入独立 RecognitionRun，历史保留并可导出 P0 prediction JSONL。
- PP-OCRv6 Small 和 Medium 使用同一完整 ONNX 检测、DB 后处理、裁图、CTC 字典解码管线；Formula 使用本地 PaddleOCR 官方模型；Qwen3-VL 4B 使用本地 MLX 权重。上述四种候选均有实际推理记录，尚无真实学生数据 Benchmark 或最终模型排名。
- Recognition Lab 位于设置的高级工具；Settings 显示依赖健康；Model Center 区分安装与 Provider 可用/已加载。
- P2 浏览器拍摄回归完成，真实 iPhone Safari 尚未验收，**P2 仍为 READY_FOR_DEVICE_TEST**。

## 下一步

1. 用户按 P2 handoff 使用真实 iPhone Safari 验收；确认通过后才能将 P2 标记 PASS。
2. 后续阶段需处理正式 Python/依赖打包与真实作业 Benchmark；当前不开始数学判分。
