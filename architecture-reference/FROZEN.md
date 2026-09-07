# Architecture Reference Freeze

REFERENCE_ARCHITECTURE_VERSION = 1.1

STATUS = FROZEN

核心参考架构、职责边界和 A/B/C 真实性口径自此冻结。后续允许更新面试知识、指标来源和勘误文档；不得因追求“更优雅”随意改变 Orchestrator、Skill、Harness、Context、State、Tool、Evidence、Progress 的既定职责。

CHANGE: Evidence-Obligation-Driven Progress Refactor

这是 v1.0 冻结后的单点架构修正：拆分 Possible/Required，新增 RequirementResolver、
Evidence Obligation 与确定性 Evaluator，并解除 Tool success 与 Dimension complete 的绑定。
没有引入 Multi-Agent、MCP、Long-term Memory、新业务 Tool 或生产基础设施。

若未来确需调整核心，必须先记录真实失败证据、影响的 Contract、兼容策略、迁移测试和版本号，不得以文档更新暗中改写已冻结语义。
