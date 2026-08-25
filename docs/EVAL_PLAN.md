# Eval Plan

`eval/evaluator.py` 已具备 8 个最小可运行样例：

- case_001：有订单号，成功获取并保存 Facts。
- case_002：缺少订单号，进入 `WAITING_USER`。
- case_003：第二轮提供订单号，恢复任务并完成。
- case_004：`ORDER_NOT_FOUND_OR_NOT_AUTHORIZED`，对外统一表述。
- case_005：可重试 Tool 暂时失败，达到上限后 `HANDOFF`。
- case_006：永久 Tool 失败，进入 `FAILED`。
- case_007：Facts Contract 不匹配，进入 `FAILED`。
- case_008：超过最大 retry 次数，进入 `HANDOFF`。

当前统计 `task_success`、`tool_success`、`handoff`、`retry_count`。接入真实 Facade/LLM 前应扩展：Intent Accuracy、Tool Selection Accuracy、Tool Argument Accuracy、Task Success Rate、Human Handoff Rate、Failure Recovery Rate、Latency、Token Cost、LLM Calls、Tool Calls、RAG Recall@K、Rerank Quality、Groundedness。
