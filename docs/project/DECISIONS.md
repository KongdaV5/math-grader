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
