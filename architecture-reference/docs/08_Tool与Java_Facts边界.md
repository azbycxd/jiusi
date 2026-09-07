# Tool 与 Java Facts：动作、权限与执行结果

## 1. 三层真实性

A：真实项目已有五个只读 Tool、Java Facts Client 和词法规则检索。
B：本目录重写为统一 AgentTool 执行壳和标准库参数 Contract。
C：真正写型 Tool、事务补偿、远程熔断与生产 Client 部署不在本批。
ReferenceStub 的 fixture 是显式测试数据，不是当前数据库事实。

## 2. 调用边界

Python Agent → Python Tool → Java Facts HTTP API。
Java 内部再进入 Domain、Repository、MySQL/Redis。
Python 不直接调用 DAO、Mapper，也不拼 SQL。
原因是业务权限、事务、一致性规则应由权威业务服务维护。
Agent 可以解释多份事实，不能绕过业务系统判断订单所有权。

## 3. 五个 Tool 的差异

| Tool | 模型参数 | 返回核心对象 | 任务信息 |
|---|---|---|---|
| get_order_facts | outTradeNo | order、references | 订单状态和可溯源实体 |
| get_activity_facts | activityId | activity | 活动状态/有效期 |
| get_user_eligibility_facts | activityId | eligibility | 可信用户的资格限制 |
| get_joinable_team_facts | activityId | candidate_teams | 候选团，可为空 |
| search_group_buy_rules | query | rules | 稳定规则文本 |

四个 Java Tool 和一个 RAG Tool 共享格式、错误与副作用边界。
每个 Tool 自己选择 Client 方法和结果 Schema。
Registry 不应出现 get_order_facts 等名称的业务分支。

## 4. AgentTool 是共同执行壳

run 先验证模型参数是否含受保护字段。
再通过 arguments_type 构建类型明确的参数对象。
从 trusted_context 提取最小 AuthContext。
执行具体 Tool 的 _invoke。
验证 result_schema 与 JSON 安全字段。
成功构造 ToolResult，失败映射稳定错误码。
未知异常只产生 TOOL_UNEXPECTED_ERROR。
原始异常文案和堆栈不进入 ToolResult。

## 5. 自描述 metadata

name 是精确注册名称。
description 解释动作，而不是开放式业务目标。
version 标明 Reference 契约版本。
arguments_schema 约束可控输入。
result_schema 约束结果对象。
repeat_policy 决定模型同参数重调限制。
timeout_ms 是动作耗时上限声明。
side_effect_level 声明副作用类型。
describe 返回模型可见子集，Client 对象和认证信息不可见。

## 6. 为什么当前只读

诊断需要查看事实和规则，不需要执行退款或修改订单。
READ_ONLY 能够使用有限瞬时失败重试。
IDEMPOTENT_WRITE 仍需幂等键和服务端语义。
NON_IDEMPOTENT_WRITE 的超时无法直接判断动作有没有发生。
枚举里有写级别，不代表项目实现了写操作。

## 7. Registry 的职责

register 只接受 AgentTool 实例，拒绝重复名称。
unregister 仅限 Reference 初始化/教学使用。
get 对未注册名称报错，不做模糊查找。
describe/list_metadata 从工具自身读取契约。
validate_arguments 委托工具参数模型。
call 校验 ToolResult 返回类型和所属名称。
repeat_policy 返回工具自身的重复调用约束。
Skill/Runtime allowlist 由 Harness 在执行前检查。
单独调用 Registry 不代表已执行完整 Harness 验证。

## 8. Schema 与 Provenance

Schema 回答“格式是否正确”。
activityId 是正整数，outTradeNo 是有界非空字符串。
bool 不能因为 Python 的类型继承被当作 int。
未知字段拒绝，不能删除 userId 后继续调用。
订单号不硬编码纯数字或固定业务长度。
Schema 合法的 activityId 仍可能是模型猜出来的。
Grounding 必须核验它来自用户输入或明确 Observation 路径。

## 9. 身份如何进入 Client

Tool arguments 不能有 userId、authenticatedUserId、Token、Header。
Runtime 提供的 RequestContext/AgentState 才是可信身份来源。
IdentityGuard 构建 AuthContext，并隐藏 repr 中的身份。
Tool 仅把 auth 作为独立参数交给 Client。
模型 Schema、ToolResult 和 Observation 不包含身份。
Reference 的 auth 对象模拟边界，不是完整认证服务。

## 10. ReferenceStub 的行为

Stub 接收按操作和实体索引的 fixture。
显式 failures 队列可模拟 timeout、connection、HTTP_503。
没有匹配数据时返回 NOT_FOUND。
订单不存在与不属于当前身份都返回统一错误。
Stub 的 calls 只记操作与实体，不记录身份凭证。
fixture 里的 owner 用于离线模拟 Java 二次权限。
不发任何 HTTP，不读取当前 Java 项目。

## 11. 结果契约与规范化

Reference 用 order/activity/eligibility/candidate_teams 规范字段。
这只是 Python 内部可读的 Facts 示例。
不宣称覆盖真实 Java API 的所有字段或状态。
真实 Client 应按 HTTP → JSON → Envelope → code → data schema 处理。
HTTP 200 不自动等价于业务 code=成功。
工厂继续检查 JSON 类型和禁止字段，形成纵深防护。
Java 数据不能包含模型 rootCause 或 recommendation 作为诊断答案。

## 12. 错误分类

TOOL_TIMEOUT、TOOL_CONNECTION_ERROR 可在只读范围内有限重试。
INVALID_ARGUMENT、AUTH_REQUIRED、NOT_FOUND 不重试。
TOOL_CONTRACT_FAILURE 表示结构不一致，应修契约或实现。
TOOL_UNEXPECTED_ERROR 默认不可重试。
失败不会生成业务 Observation。
success=True 且 participation_limit_reached=True 完全合理。
这是查询成功、业务参与受限，不是“查询失败”。

## 13. 超时的诚实边界

Reference 记录耗时，超过声明时间可映射 TOOL_TIMEOUT。
它无法中断正在阻塞的任意 Python 函数。
生产 HTTP Client 必须设置连接/读取超时和取消机制。
不能把完成后的计时误称为强制传输超时。

## 14. 未来写型工具

写操作需要用户确认、权限、幂等键与审计。
是否成功应由业务服务明确回执。
超时后的处理可能是查幂等结果，而不是重复写。
补偿与回滚需要业务语义，不能由通用异常捕获替代。
这些都是 C 层生产扩展。

## 15. 验证与面试

测试覆盖五个 Tool 返回契约、订单所有权、未知异常和字段错误。
候选团空集合单独走完整 Evidence 测试。
面试中应说“统一自描述只读动作，权威事实仍在 Java”。
不能说“Python Agent 接管了 Java 事务和业务数据库”。
