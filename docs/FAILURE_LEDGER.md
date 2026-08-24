# Failure Ledger

任何接入真实系统后的故障都应记录在此账本，并在确认修复后增加回归 Eval。

| 日期 | 现象 | 触发条件 | Root Cause | 所属层 | 修复方案 | 加入 Regression Eval |
| --- | --- | --- | --- | --- | --- | --- |
| 待记录 |  |  |  | AUTH / STATE / ROUTING / TOOL / JAVA_API / RAG / LLM / TERMINATION / PERSISTENCE / OBSERVABILITY |  | 是/否 |
| 2026-08-25 | 进程重启或多实例时会话不可恢复 | SessionMemory 仅为进程内字典 | V1 有意不接持久化存储 | PERSISTENCE | 延期到真实部署设计；评估 Redis、TTL、版本与并发策略 | 是 |
| 2026-08-25 | Trace 时长只覆盖局部步骤，未形成完整请求生命周期指标 | 当前只需最小结构化事件 | V1 未实现全链路计时/指标系统 | OBSERVABILITY | 延期到真实 Java/LLM 接入后的指标设计 | 是 |
| 2026-08-25 | evidence 与历史 ToolResult 可能随长会话增长 | V1 仅验证控制骨架 | 尚未设计 Context 压缩或保留策略 | STATE | 延期到长会话与 LLM Context 设计 | 是 |

不得把凭证、完整认证头、密码或无关用户敏感数据写入账本。
