# 从执行结果到可引用事实

## 1. 对象边界

ToolResult 描述一次执行发生了什么。
Observation 描述一次成功查询获得的业务快照。
Evidence 描述快照中可以被答案引用的具体字段。
ParameterProvenance 描述下一次工具参数的来源。
四者有数据联系，不能合并为同一个任意字典。

v1.1 另增加 Evidence Obligation：它判断信息收集是否充分；最终 `used_evidence` 判断答案
具体引用哪些事实。两者相关但不是同一 Contract。

## 2. ToolResult 字段

tool_name 绑定执行工具。
success 表示执行与契约成功。
data 仅成功时允许存在。
error_code 是稳定失败分类。
error_message 是安全固定文案。
retryable 是声明，由 Runtime 政策再约束。
source 区分 Java Stub 与 Rule Catalog。
duration_ms 是实际测得耗时。
attempt 记录首次调用或自动重试。
metadata 只允许技术计数白名单。

## 3. 业务失败与查询成功

资格查询返回 participation_limit_reached=True。
这意味着服务已经给出了可用事实。
ToolResult 应为 success=True。
活动关闭同样不是传输失败。
无法连接 Java 才是 TOOL_CONNECTION_ERROR。
错误混层会让 Agent 重试一个永远不会改变的业务条件。

## 4. 工厂流程

ToolResult.success=False → 不创建 Observation。
ToolResult.success=True → 对象结构校验。
随后递归 JSON 检查与敏感字段拒绝。
形成独立 Observation ID 和时间戳。
按路径提取 Evidence，连同 sequence_no 返回。
上游 Tool 已验证 result_schema，工厂再做通用数据边界检查。

## 5. 脱敏的失败语义

这里不是“把敏感字段偷偷删掉再继续”。
出现 token、header、sql、source_files 等字段时拒绝构造。
原因是静默删字段可能掩盖下游契约漂移。
普通 JSON 原始值保留。
NaN、自定义对象和不可寻址字段名拒绝。
返回对象以深拷贝与工厂快照避免原输入污染。

## 6. Observation 身份

observation_id 区分同 Tool 多次执行。
tool_name 表示它来自哪个受限动作。
data 是经过验证的业务值。
source 标明事实来源类型。
created_at 与 sequence_no 提供时间和顺序。
evidence 是从同一快照提取的引用集合。
Registry 不相信外部传入 evidence 已经正确，而会重建索引。

## 7. Path 的含义

activity.status 是对象叶子。
candidate_teams[0].team_id 是数组元素叶子。
candidate_teams 是空数组本身。
不存在路径抛 KeyError。
负数组索引拒绝，避免 Python 从尾部读取意外数据。
越界索引拒绝，不返回 None 冒充合法缺省值。
has_path 检查的是存在，不检查值真假。

## 8. 空数组 Bug

旧式写法常使用“if value”决定是否添加 Evidence。
这会把 []、False、0、None 一起丢弃。
候选团查询成功且 candidate_teams=[] 时，用户最关心的结论恰恰是“没有”。
如果丢弃证据，模型会无法给出有依据的空结果回答。
正确做法是以路径存在和结果成功为判断依据。
extract_evidence 对空容器直接创建叶节点。
测试明确验证候选团查询成功、Observation 成功、Evidence 存在、值等于 []。
candidate_teams[0] 此时必须不存在。

## 9. 同一工具多个版本

完整 Evidence ID 使用 observation_id:path。
阅读时允许 tool_name.path 短名。
当同一个 Tool 又产生相同 path，短名不再唯一。
Registry 拒绝解析歧义短名，要求明确版本。
不能让旧答案引用悄悄指向新快照。
相同 Observation ID 对应不同内容时也拒绝注册。
Reference 不用“最新值覆盖”掩盖冲突。

## 10. EvidenceRegistry 接口

register_observation 注册经过验证的事实副本。
resolve 解析精确 ID 或唯一短名。
exists 只检查索引存在。
list_available 返回可用证据副本。
validate_used_evidence 校验引用和值。
Evidence 对象如果复制 ID 后篡改 value，会被拒绝。
布尔 True 不能冒充整数 1，尽管 Python 比较可能认为相等。
空 Evidence 列表对实例业务答案默认拒绝。

## 11. 不能引用什么

available_tools 说明能力，不说明业务状态。
source_files 说明实现来源，不是用户订单事实。
Prompt 文本和模型自报结论不创建 Observation。
完整 ToolResult 失败历史不是事实集合。
认证 Header 与可信身份不进入 Evidence。
RAG 证据只支持规则解释，不自动支持当前资格判断。

## 12. 参数链的例子

订单返回 references.activity_id=7。
模型想调用候选团查询 activityId=7。
Provenance 记录 parameter_name=activityId。
parameter_value=7，source_type=OBSERVATION。
source_path=references.activity_id。
source_observation_id 指向那一份订单事实。
Guard 对照真实路径，检查三方值与类型都相同。

## 13. 参数来源不是答案证据

下一份候选团 Observation 返回 candidate_teams=[]。
答案“当前没有候选团”使用候选团空数组 Evidence。
不要求答案把内部 activityId 查找过程当成业务结论。
Provenance 支持执行链审计；Evidence 支持回答事实审计。
即使执行参数来自 RUNTIME，也必须对照可信代码提供的账本。
UNKNOWN 或自报路径但没有原 Observation，稳定拒绝。

## 14. 能证明与不能证明

Guard 能证明引用存在、版本明确、原值相同。
它不能证明任意自然语言推论全部正确。
模型可能引用真实 evidence 却做出错误解释。
这要通过行为 Eval 和人工样本审查识别。
不能把 EvidenceGuard PASS 等同于生产“准确率 100%”。

## 15. 测试与调试

test_tool_result_observation 检查成功/失败分流。
test_empty_list_evidence 检查 falsey 值。
test_evidence_guard 检查路径、数组索引、内部字段、版本歧义和篡改。
test_parameter_grounding_guard 检查多跳参数。
定位错误时先看事实是否取得，再看提取/索引，再看引用和模型解释。

## 16. Evidence Obligation 与 Tool Contract 分离

Tool Contract 回答“这次调用是否按自身接口成功”。Task Completion Contract 回答“当前
Query 所需事实是否已经充分”。Activity Tool 只返回 status 仍可 success 并生成 Observation；
若 `activity_validity` 还要求 within_valid_time，则 Obligation 保持 PENDING。禁止为了让
success 等价 complete，反过来把所有任务字段强塞进 Tool result_schema。

## 17. EXACT、PREFIX 与 falsey 值

EXACT 要求完整 Evidence 别名精确存在。PREFIX 用于非空规则条目，例如匹配
`search_group_buy_rules.rules[`；`rules=[]` 只生成 `rules` 空集合 Evidence，因此不满足该
PREFIX。候选团队义务使用 EXACT `candidate_teams`，所以 `[]` 可以满足。false、0、Contract
允许的 None 都按 EvidenceRegistry.exists/叶节点存在性处理，不使用 truthiness。

## 18. 多来源而非固定 Tool

Condition 的 accepted_paths 可以同时列 Tool A 与 Tool B 的等价可信路径；任一真实
Observation 都可满足。Evaluator 只重建 Registry 并匹配路径，不调用 LLM、不解释值、
不接受外部伪造 evidence_refs。这证明 Obligation 约束 Evidence，不约束固定 Tool 名。
