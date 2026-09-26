# DECISIONS.md

## 已冻结的项目决策

- **D-001 正式产品不依赖 27B**：本地 Qwen3.8 27B IQ3 只用于开发辅助。
- **D-002 模板优先**：固定教辅页面采用“页面配准 → 答案区域裁剪 → 小区域识别”，不让大模型每次整页理解。
- **D-003 确定性判分**：OCR/VLM 负责识别；最终对错由标准答案与 Python 规则引擎决定。
- **D-004 安全优先**：无法可靠判断时进入 `REVIEW_REQUIRED`，不猜答案。
- **D-005 学生信息长期保存**：首次录入后复用。
- **D-006 多页 Submission**：拍一页后不切学生；点击“完成该生”后才锁定并进入下一学生。
- **D-007 手机采集、Mac 计算**：默认同一局域网 Capture Bridge。
- **D-008 每页立即上传**：不等待“完成该生”后批量上传。
- **D-009 Codex 默认 Luna**：Terra 仅复杂跨模块；Sol 仅真正必要时使用。
- **D-010 P0 先于完整产品开发**：P0 未完成前不开发完整客户端。
- **D-011 P0 质量门槛**：自动判分 Precision 目标 ≥99.5%，初期自动处理率目标 ≥80%。
- **D-012 P0-W1 不锁死模型**：只建立 Benchmark Foundation；模型选择留给后续真实 Benchmark。
- **D-013 阶段顺序调整**：P0-W1 Benchmark Foundation PASS 后先做 P1 Application Foundation；P0-W2 不再紧跟 P0-W1，模型 Benchmark 延后到 P6 Recognition Integration 之后。
- **D-014 P1 本地应用栈**：Tauri 2 + React + TypeScript + Python 标准库本地服务 + SQLite migrations；Desktop 通过 HTTP 调用服务，不能直接访问 SQLite。
- **D-015 P1 Mock Recognition 边界**：Submission 流程只依赖 Recognition Gateway 和 Provider 注册表；P1 使用可配置 Mock Provider，不接真实 OCR/VLM，不把 P0 Benchmark 输出当模型表现。
- **D-016 Submission 队列与状态机**：状态迁移集中管理；SQLite 保存顺序 Job Queue、结果和失败；只有“完成该生”才入队，多页采集不自动切换学生。
- **D-017 Capture Bridge 网络边界**：Desktop API 仅绑定 loopback；明确开启 Capture Session 后，另一个监听器才绑定用户选择的 RFC1918 LAN 地址，且只提供 Capture 页面与最小 Capture API。会话 token 使用 256-bit 随机值，数据库只存 SHA-256，Session 结束、过期或服务重启后失效。
- **D-018 每页即时保存与重复保护**：手机确认保留后立即以图片 body 上传；服务校验 MIME 与文件签名、10 MB 上限、当前 Submission ID 和 UUID Idempotency-Key，再使用内部 page UUID 落盘并保存文件名、MIME、字节数、上传时间与 SHA-256。客户端文件名不用于磁盘路径。
- **D-019 明确 finish 与队列并行**：只有确认“完成该生”才把当前 Submission 原子地变为 READY / QUEUED、创建一个 Queue Job 并选择下一位 active student；重复 finish 幂等。前一位后台处理时，手机可继续采集下一位；最后一位完成后 Session 不回到名单开头。
- **D-020 P3-X1 可与 P2 设备 Gate 并行**：P2 保持 `READY_FOR_DEVICE_TEST`；从指定 `phase/p2` HEAD 创建 `phase/p3-x1`，不合并 main。真实 iPhone 验收和修复后续独立回合处理。
- **D-021 统一运行数据目录**：正式 macOS 新安装使用 `~/Library/Application Support/MathGrader/`，统一由 `RuntimePaths` 提供 data/images/models/cache/logs/config；旧 P1/P2 数据原位读取，不做自动搬迁。
- **D-022 模型候选与安装分离**：版本化 Catalog 只记录候选来源；模型文件仅在用户显式安装时进入 Application Support 的 `models/`，先 staging、验证后原子落盘。Qwen 原始模型与 MLX Community 转换版分别标注，最终默认模型由后续真实 Benchmark 决定。
- **D-023 Provider 边界**：Submission 继续依赖 Recognition Gateway；模型 Provider 按 Catalog ID 延迟发现与加载。P3-X1 不把未实现的 OCR 后处理或公式推理说成真实识别能力。
- **D-024 图像与模板渐进接入**：原图保留，ImagePipeline 手动生成 processed 副本，不自动加到 P2 上传路径；TemplateGroup/PageTemplate/Question/AnswerRegion 使用独立 migration 和归一化 0..1 坐标。
- **D-025 P4 后台图像作业**：手机确认上传后先安全保存原图并快速返回；复用 SQLite jobs/worker 处理 ImagePipeline，图像质量异常记 WARNING，可继续绑定模板与裁图；无法解码等错误记 FAILED。
- **D-026 模板绑定与历史语义**：AnswerRegion 坐标统一为 0..1，保存前严格校验；题目和区域修改提升模板版本。每次 SubmissionPage 人工绑定保存模板和 processed image 快照，旧 Crop/RecognitionRun 不随模板编辑静默改变。
- **D-027 模板候选不自动绑定**：ORB/RANSAC 只提供候选分数，低分返回 `NO_CONFIDENT_TEMPLATE_MATCH`；老师明确选择后才建立 binding。
- **D-028 候选识别与判分分离**：P4 使用真实 Small/Medium OCR、Formula 与 4B VLM 生成可追溯 RecognitionRun；路由与 fallback 仅在错误/不可用或人工指定时触发，不以猜测阈值决定最终对错。P0 export 仍标记 `REVIEW_REQUIRED`，Ground Truth 独立。
- **D-029 模型版本与运行边界**：模型仅经 ModelManager 显式安装并记录 resolved revision；Provider 只使用本地路径，不增加云端 fallback。Qwen 4B 的业务 prompt 放在 Strategy，Provider 接受调用方 prompt；8B 本轮不安装。
- **D-030 P4 发布边界**：开发机 Python 3.12 独立环境验证真实 Formula/MLX；正式 `.app` 仍从系统 Python 启动，Python 与依赖尚未打包。设置页显式展示缺失依赖，发布前必须解决，P4 不做完整 bundling 重构。
- **D-031 旧数据与新模型共存**：若 Tauri 仍读取旧 bundle-id 数据库且旧模型目录没有安装清单，ModelManager 使用标准 `Application Support/MathGrader/models`，避免旧数据兼容模式遮蔽已正式安装的模型。应用退出时显式关闭其本地服务；本地开发可用绝对路径 `MATH_GRADER_DATA_DIR` 隔离测试数据。
