# State 与 Memory：当前任务如何可靠继续

## 1. 真实性与本批范围

A：真实项目有 AgentState、进程内 SessionMemory、同身份 WAITING_INPUT 恢复。
B：本 Reference 提供明确 task_id、深拷贝、版本检查和内存 TaskStore。
C：Redis Checkpoint、分布式锁、长期记忆、后台 TTL 清理尚未实现。
本批完善的是 B 层内存行为，不把它称为生产多实例方案。

## 2. 三个容易混淆的对象

AgentState 是一项业务任务的 Working State。
它保存进度、事实、待补参数以及控制计数。
SessionMemory 保存 State 的副本，决定之后能否找回任务。
Trace 保存执行事件，帮助解释为什么走到当前状态。
把 Trace 全部塞进 State 会造成恢复载荷膨胀。
把聊天历史等同于 State 会让控制规则难以验证。
把 Memory 当作事实源会引入过期订单或资格。

## 3. 为什么保留 task_id

session_id 表示会话作用域，不足以区分会话内的多件事。
task_id 标识“本次参与失败诊断”这一目标。
用户补充活动标识，仍属于同一个 task_id。
用户突然询问标签规则，应由任务切换策略显式创建新 Task。
存储不会仅凭一条文本自动决定是否换题。
Router 或用户操作表达切换意图，TaskStore 执行确定动作。

## 4. SessionMemory 的接口

| 方法 | 输入 | 输出与失败 |
|---|---|---|
| save | State、可选 expected_version | 保存副本，返回新版本 |
| load | Session、可信身份 | State 副本或 None |
| exists | Session、可信身份 | 只判断当前身份作用域 |
| delete | Session、可信身份 | 删除当前身份快照 |
| resume | Session、身份、补充信息 | 恢复原目标，返回新快照 |
| load_or_create | RequestContext | 兼容已有参考入口 |

load 不返回内部对象引用。
save 同样复制输入，保存后修改原对象不会污染 Memory。
这使测试能够明确区分“调用方临时修改”与“已经持久化修改”。

## 5. 身份隔离不是只检查一次

存储键使用 Session 与可信身份的组合。
读取、恢复、删除、列出任务都必须带可信身份。
不同身份使用同一个 Session ID，无法读到另一人的 State。
模型提供的 userId 不能作为这些方法的 identity。
RequestContext 必须由可信 Gateway 创建。
本地字符串隔离只模拟边界；不替代生产认证。

## 6. 两轮恢复的具体过程

第一轮输入：“为什么不能参与这个活动？”
任务保存 current_query、pending_user_query 和 missing_information。
任务状态进入 WAITING_INPUT，已有 Observation 不清空。
第二轮补充：“活动是 7”。
resume 检查相同身份与 WAITING_INPUT，再组合原目标与新信息。
missing_information 清空，状态恢复 REASONING。
Progress 保留，下一轮可以继续调查。
空补充内容抛错误，不能让任务假恢复。
终态不可通过 resume 重新打开。

## 7. 快照与版本

第一次保存的当前存储版本视为 0，保存后返回版本 1。
之后可以携带 expected_version 作比较再写入。
两个调用方都拿到版本 1，第一个保存成版本 2。
第二个再提交 expected_version=1，会得到 STATE_VERSION_CONFLICT。
冲突表示应重新加载并处理，不应静默覆盖。
这里的比较逻辑是单进程 Reference。
没有锁或事务，不宣称线程/多实例下的原子 CAS 已经完成。
生产实现可用 Redis WATCH/Lua 或数据库条件更新实现原子比较。

## 8. TaskStore 的数据组织

内部任务键为 Session、可信身份、task_id。
active_task_id 按 Session 与身份保存当前激活任务。
暂停集合只记录调度状态，不改写原始 WAITING_INPUT。
因此暂停后回来，原问题与缺失字段仍然存在。
get_task、list_session_tasks 返回副本。
update_task 比较 State 版本，防止陈旧快照覆盖。

## 9. 切题例子

Task A：参与诊断，缺 activityId，处于 WAITING_INPUT。
用户改问标签规则，调用方创建 Task B。
TaskStore 暂停 A，激活 B。
B 的 Observation 和 Progress 从空任务开始。
用户返回 A，调用 resume_task 或 switch_task。
恢复的是 A 的原始目标，不把 B 的规则回答当 A 的实例事实。
无效目标切换先报错，不清除当前 active 指针。
已完成任务不得重新作为活跃任务。

## 10. 完成、删除与保留

complete_task 标记完成并解除 active_task_id。
Reference 保留已完成快照用于阅读与测试。
SessionMemory 可显式删除当前任务。
生产需要定义保留期限、删除范围和审计依据。
不能无期限保存带业务标识的全部任务内容。

## 11. LongTermMemory 为什么只是协议

长期稳定偏好、历史诊断摘要、历史问题线索可以成为候选记忆。
原始认证信息、完整堆栈、未治理聊天内容不能直接写入。
昨天的订单 CLOSE 或资格限制不能当今天实时事实。
历史摘要只能提示“曾经调查过什么”，随后重新查 Java Facts。
MemoryEntry 记录 source_task_id、user_scope、创建与过期时间。
write/retrieve/delete/expire/list 均需约束身份。
TTL 是过期机制，不意味着删除已经完成所有备份和索引清理。

## 12. Checkpoint 与业务 Memory

Checkpoint 保存恢复程序执行所需的完整状态。
长期 Memory 保存可复用的稳定摘要或偏好。
二者的数据形状、保留期限、隐私要求不同。
生产 Checkpoint 还要处理恢复后重复动作。
只读查询可重新执行；写动作必须额外设计幂等。
本批没有把写动作恢复或 Redis 当作已实现能力。

## 13. 如何验证

test_session_memory 验证 save/load 深拷贝、身份隔离、版本冲突和恢复。
test_task_store 验证切题、原目标保存、跨身份隔离和失败切换。
测试只用内存，不连接 Redis。
这些结果支持确定性行为结论，不支持 QPS、SLA 或多实例一致性结论。

## 14. 面试回答

“为什么不存完整聊天记录？”
任务恢复需要结构化控制状态和有效事实，全历史会增加隐私与冲突成本。
“为什么需要深拷贝？”
避免调用者修改已保存状态，明确何时才算一次提交。
“什么时候上 Redis？”
当部署多个实例、需要重启恢复时，再设计原子版本更新、TTL 和身份命名空间。
