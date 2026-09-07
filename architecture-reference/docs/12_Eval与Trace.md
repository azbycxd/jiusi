# Eval 与 Trace

## 1. Eval 分层

1. Unit/Contract Test：Schema、Guard、Registry、状态转换等确定性边界。
2. Deterministic Harness Eval：固定 Decision/Stub 下验证能力、参数、Evidence、预算。
3. Real Provider Behavior Eval：观察真实模型 Tool 选择、结构契约与 Bad Case。
4. Real HTTP E2E：Client→HTTP→Runtime→LLM→Java/RAG→Response。
5. Retrieval Eval：只衡量召回，不混入生成质量。
6. Security Eval：Injection、越权、跨 Session、Evidence 伪造。
7. Performance Eval：Latency、Token、Cost、QPS 和饱和行为。
8. Regression Dataset：把线上/评测 Bad Case 固化并持续回归。

当前真实项目已有确定性测试、真实 Provider 行为评测、HTTP E2E 和 Retrieval baseline；
大规模 Gold Dataset、线上 A/B 和生产 SLA 尚未完成。

## 2. 已有阶段数据的正确表达

- 42/42 real behavior sweep；
- 12/12 targeted dynamic chain；
- 23/23 final HTTP audit；
- 当时 Python suite 192 passed；
- Retrieval Top-1 70%、Top-3 100%、无关 Query 5/5 空；
- 最终开放式诊断 17/20 FULL、0 PARTIAL，剩余 Provider timeout 转 HANDOFF。

这些数字来自不同阶段、不同数据集和不同评测目的，不能相加，也不能概括成“准确率
100%”。Provider timeout 要归 PROVIDER/INFRA，不应记为业务诊断错误。

## 3. Retrieval Eval

Case 明确 relevant_document_ids、forbidden_document_ids、expected_top_k 和 expected_empty。
Recall@K 衡量相关文档覆盖；Precision@K 衡量结果纯度；MRR 看第一个相关结果位置；
HitRate@K 看至少命中一次；NDCG 可用于多级相关性。空结果 Case 防止系统强行召回。

## 4. Answer Eval

Retrieval 正确不等于生成正确。Answer 应分别评价 Correctness、Faithfulness、Relevance、
Completeness 和 Unsupported Claim Rate。Evidence Guard 能验证引用存在与原值，不能单独
证明自然语言因果推论正确。BLEU/ROUGE 对开放式业务表达只可作辅助。

## 5. LLM Judge（C）

JudgeInput 包含 user query、reference facts、retrieved context、model answer 和固定 rubric；
JudgeResult 返回总分、分维度得分和简短 reason_summary，不要求隐藏思维链。生产应固定
Judge Prompt、Rubric、模型版本，使用低温/确定性设置，并人工复核低分、临界和争议 Case。
风险包括 judge bias、position bias、self-preference、model drift。

## 6. Eval 状态与 Failure 分类

结果明确区分 PASS、FAIL、INFRA_FAILURE。FailureClassifier 包括 ROUTING、SKILL_SELECTION、
CONTEXT、MODEL_DECISION、TOOL_SELECTION、TOOL_ARGUMENT、TOOL_EXECUTION、RETRIEVAL、
RERANK、EVIDENCE、COMPLETION、PROVIDER、INFRA、BUSINESS。分类应链接到对应 Trace Span，
不能只给一个“Agent Failed”。

## 7. Trace 结构

Trace 按 trace_id 聚合多个 TraceSpan 和 TraceEvent。Span 有 span_id、parent_span_id、
session_id、task_id、skill_name、stage、start/end/duration、status、error_code、metadata。

Span 类型覆盖 REQUEST、ROUTING、SKILL_LOAD、CONTEXT_BUILD、MODEL_CALL、
DECISION_VALIDATION、TOOL_CALL、TOOL_RESULT、OBSERVATION、PROGRESS_UPDATE、COMPLETION、
FINAL_ANSWER、HANDOFF、ERROR。父子关系可重建完整关键路径。

## 8. Trace 脱敏

TelemetrySanitizer 禁止 API Key、Token、Authorization、完整 Header、可信 user ID 明文、
SQL、Java stack、完整 Prompt 与 Provider raw response。可以记录模型名、Token usage、
Tool name、允许参数摘要、错误类别、latency 和安全内容摘要。脱敏在写入 Trace 前完成，
不能依赖日志平台事后删除。

## 9. Metrics

Reference 支持 Counter、Histogram 和 Gauge。核心 Counter：task_total/task_success/
task_handoff、model_calls/model_failures、tool_calls/tool_failures/tool_retries/model_retries、
evidence_failures、retrieval_hits。Histogram：latency_ms、model/tool latency、context/input/
output token。Gauge 可表达队列深度、并发和 breaker 状态。

## 10. Eval 与 Trace 的关系

Eval 说明“是否满足预期”，Trace 说明“在哪一层、哪一步、因为什么失败”。例如正确
文档未进 Top-K 映射 RETRIEVAL Span；Top-K 正确但答案无依据映射 MODEL/FINAL_ANSWER；
Tool timeout 映射 TOOL_RESULT；Evidence 路径不存在映射 FINAL_ANSWER/EVIDENCE。

Trace 不是 State：它不能恢复任务。State 不是 Trace：它不应该为观测目的保存完整
Prompt/Provider Response。两者用 trace_id/task_id 关联。
