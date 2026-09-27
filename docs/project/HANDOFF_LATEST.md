> 项目知识入口已于2026-09-26收敛到 [Obsidian canonical Status.md](</Users/kongda/Documents/Obsidian/obsidian-vault/Projects/Math-Grader/Status.md>)。以下原文保留为历史/clone技术参考，不再独立更新当前项目状态；其中PASS仅对应原阶段证据。

# 最新交接

- 工作包：**P5-L2 — Production Runtime Packaging + Standalone Desktop Delivery**
- 状态：**PASS**。最终 Native Gate 已验证 Submission Workspace 照片及大图预览、P5 Teacher Workflow、人工复核与成绩、bundle runtime、服务生命周期和冷启动。首次检查发现的 CSP 图片阻塞与缺少隔离流程数据已关闭。
- Branch：`phase/p5-l2`
- Start SHA：`3d102bd24ddd56d0a5ac8380cfdee721e50574c7`
- Code Implementation End SHA / final app manifest SHA：`295dfede7530bb7986ade6f01008d038535bf6f8`
- 完整交接：[P5-L2-2026-09-26.md](handoffs/P5-L2-2026-09-26.md)

最终 `.app` 构建路径为 `desktop/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Math Grader.app`，安装在 `/Applications/Math Grader.app`，大小约 1.3 GB。内含 CPython 3.12.14 arm64 与锁定依赖，不回退到系统 Python；模型权重不在 app 内。本地 ad-hoc 签名验证通过；未公证，hardened runtime 关闭。目标为 macOS 15.0+ Apple Silicon。

验证包括 Python **108 passed**（最后 Python 回归在 UI-only 原图预览修复之前，Python 源码之后未变）、`compileall`、`uv lock --check`、TypeScript/Vite build、前端坐标和 Capture URL 测试、arm64 Tauri release build、runtime/CSP bundle verifier、`codesign --verify --deep --strict`、真实包内 ImagePipeline/PP-OCR/Formula/Qwen 4B smoke，以及合成 Student A/B P5 流程。测试数据为合成内容；没有真实学生照片或准确率结论。

首次 Native Gate 历史：原生 Tauri 图片曾因 `img-src` 缺少 loopback image service 而不能显示，正式用户 profile 也没有完整 P5 样本。其后 `img-src` 精确增加 `http://127.0.0.1:8765`，没有 wildcard / 通用 `http:` / LAN；使用隔离 fixture 在原生 Submission Workspace 和 Human Review 显示四页图片。

Native Gate fixture 结果：Student A 四页、Assignment 临时模板一次确认、实际处理一项人工复核后最终 `4/8`；Student B 四页复用同一模板、不重新整页分析，`8/8`。普通老师入口可选择 `P5 Native Gate Sample Book · Native Gate Fixture`，并能看到新试卷分析按钮；本轮未触发新模型分析。测试 provider 明确 `inference_performed=false`，fixture 已清理，未改正式 Application Support 数据。

最终 `/Applications` App manifest / About SHA 为 `295dfede7530bb7986ade6f01008d038535bf6f8`。8765 自动启动、8766 未开启；Cmd-Q 后两端口和 service 进程退出；冷启动恢复隔离数据。P2 仍为 **READY_FOR_DEVICE_TEST**，真实 iPhone Safari 未验收。未开始 P6 Benchmark / Confidence。

历史交接：[P5-L1-2026-09-26.md](handoffs/P5-L1-2026-09-26.md)、[P4-X1-2026-09-26.md](handoffs/P4-X1-2026-09-26.md)、[P3-X1-2026-09-25.md](handoffs/P3-X1-2026-09-25.md)、[P2-2026-09-25.md](handoffs/P2-2026-09-25.md)。未 push，未合并 main。
