# START HERE — Math Grader

## 当前阶段

**P0-W1 Benchmark Foundation：PASS。**

**当前工作包：P1-W1 Application Foundation。**

P1 完成后停止并交接，不自动开始 P2。

## 当前阶段顺序

```text
P0-W1 Benchmark Foundation 已 PASS
↓
P1 Application Foundation
↓
P2 Capture Bridge
↓
P3 Image Pipeline
↓
P4 Template System
↓
P5 Recognition Integration
↓
P6 Model Benchmark
↓
Normalize / Grader / Confidence / Student History / Analytics / UI 完善
```

P0 的 Benchmark 子系统永久保留，但真实模型 Benchmark 延后到识别接入及应用管线形成之后。P1 使用 Mock Provider，不下载模型、不接真实 OCR，也不开始 P2。

## 应用开发方式

- Desktop：Tauri 2、React、TypeScript；
- Local/Core Service：Python 标准库 HTTP 服务；
- Storage：SQLite migrations；所有数据库读写经本地服务；
- Recognition：统一 Gateway 与 Provider 注册表；P1 只接 Mock Provider；
- Queue：SQLite 持久顺序队列，后台 worker 失败后继续处理后续任务；
- 多页流程：拍一页不会切学生，只有点击“完成该生”才排队。

从项目根目录运行 P0 与 P1 测试：

```sh
.venv/bin/python -m pytest
.venv/bin/python -m compileall -q benchmark local_service tests
```

从 `desktop/` 运行 React UI 检查：

```sh
npm install
npm run typecheck
npm run build
npm run desktop:dev
```

Tauri 原生开发还需要 Rust/Cargo；Python 服务要求 Python 3.9+。浏览器 demo 可用 `npm run demo:dev` 同时启动本地服务和 React 页面。

## 工程纪律

- 已 PASS 的 P0-W1 不重做；
- 不开始 P0-W2 Model Benchmark，除非进入 P6 并单独授权；
- 不开始 P2 Capture Bridge；
- 不下载 PP-OCR、Qwen-VL 或其他模型；
- 保护本地作业照片，不跟踪用户测试数据；
- 当前任务由一个代码 Writer 连续完成，Reviewer 不直接改代码。
