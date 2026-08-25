# Phase 2C-2.1 OpenAI Real LLM Live Integration 验收

## A. 实际模型名

不可用。验收时在指定 Conda `group-buy-agent` 进程中检查到 `LLM_MODEL: configured=false`。为避免泄露信息，只检查存在性，未输出或读取任何密钥值。

## B. OpenAI 真实调用是否成功

否。`LLM_API_KEY`、`LLM_MODEL`、`LLM_BASE_URL`、`LLM_TIMEOUT` 在执行 `conda run -n group-buy-agent ...` 的进程中均为 `configured=false`。因此没有构造或发送真实 Provider HTTP 请求。

## C. 场景 A 真实 Decision

NOT_TESTED。未将“你能帮我做什么？”发送给 FakeDecisionModel、MockTransport 或 Stub，不能在没有真实配置时伪造 `ANSWER` / `tool_call_count = 0` 结论。

## D. 场景 B 完整调用链

NOT_TESTED。没有真实 LLM 首次决策，故未启动：

```text
OpenAI → CALL_TOOL → get_order_facts → JavaMarketClient → Java → MySQL
→ Observation → OpenAI 第二次调用 → ANSWER
```

本次未访问或修改 Java 项目源码。

## E. 场景 B 第一次 Model Decision

NOT_TESTED。没有真实 Provider 响应，因而没有可报告的 `CALL_TOOL`、Tool 名称或参数。

## F. Java 真实 Facts

NOT_TESTED。为避免把已有历史结果或测试替身误作本次结果，没有直接调用 `JavaMarketClient`，也没有报告旧数据库 Facts。

## G. 场景 B 第二次 Model Decision

NOT_TESTED。没有第一次真实 Tool observation，故没有第二次真实模型 Context 或 Decision。

## H. 最终 ANSWER 及 used_evidence

NOT_TESTED。没有真实最终答案或 `used_evidence` 可由 Harness 验证。

## I. 场景 C 结果

NOT_TESTED。未将“我的退款什么时候到账？”发送到真实模型；没有使用常识、Fake 或 Stub 冒充安全 `HANDOFF` 行为。

## J. Model 调用次数 / 耗时 / token usage

真实模型调用次数为 `0`；无真实模型名、时延、重试或 token usage。没有伪造 telemetry。

## K. Trace

无真实模型或 Agent live Trace。没有写入 API Key、认证 Header、可信身份、完整 Prompt、Provider response 或内部 stack。

## L. Bad Cases

唯一阻塞项：用户所称的 LLM 环境配置没有传递到当前 Codex/Conda 运行进程。检查结果仅为布尔状态：

```text
LLM_API_KEY: configured=false
LLM_MODEL: configured=false
LLM_BASE_URL: configured=false
LLM_TIMEOUT: configured=false
JAVA_MARKET_BASE_URL: configured=false
JAVA_MARKET_ENABLE_DEV_AUTH_HEADER: configured=false
```

项目根目录也不存在已加载的 `.env` 文件。本次未修改任何业务代码。

## M. pytest 结果

执行：

```powershell
conda run -n group-buy-agent python -m pytest -q
```

结果：`49 passed in 0.34s`。

## N. 是否修改业务代码

否。本次只新增本验收报告；没有改变 Agent、LLM Adapter、Tool、Java Client 或 FastAPI 业务实现。

`OPENAI_API_CONNECTIVITY = FAIL`

`REAL_LLM_FIRST_DECISION = FAIL`

`LLM_TOOL_JAVA_MYSQL_LLM_LOOP = FAIL`

`UNSUPPORTED_QUERY_SAFETY = FAIL`

`V1_REAL_LLM_LOOP = FAIL`
