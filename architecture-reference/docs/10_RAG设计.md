# RAG 设计

## 1. 当前真实实现（A）

当前知识库是 15 条人工治理的 Rule Entry，不是 PDF 大文档、固定 Token Chunk、
Embedding、Vector DB、Hybrid Search 或 Cross Encoder。每条 Rule 本身就是一个完整
语义原子：`Rule Entry → Lexical Retriever → Top-3 → RAG Observation → Evidence →
DecisionContext`。

已有专项评测：Top-1 Hit 70%，Top-3 Hit 100%；5 条无关 Query 全部返回空结果。
这些是当前 Catalog 和评测 Query 的阶段结果，不是通用生产 SLA。

## 2. KnowledgeEntry

模型可见字段是 knowledge_id、title、category、content、requires_realtime_facts。
内部治理字段是 tags、source_level、version、updated_at、source_files、source_symbols、
generated_from 等 internal_metadata。内部文件路径既不是业务知识，也可能泄露仓库结构，
因此只用于治理、审计和更新，不进入模型 Context 或 Evidence。

`requires_realtime_facts=true` 表示规则解释必须结合 Facts，不能从规则推断某用户当前
资格、订单或活动状态。

## 3. 当前 Lexical 算法

Reference 完整表达当前思路：NFKC/lowercase/空白 normalize；提取 ASCII token；中文
连续文本形成 bigram；分别计算 title、category、tags、content 重合；再叠加 contains
和 exact boost。字段分数进入 score_breakdown，总分降序且 knowledge_id 稳定打破平局。
只返回超过阈值的 Top-K，零匹配返回空而不是硬凑三条。

RetrievalHit 保存 Entry、总分、字段分解与各 Retriever rank；RetrievalResult 保存原
Query、hits、top_k、minimum_score，供 Trace 和 Eval 定位。

## 4. 为什么当前没有传统 Chunk

一条 Rule 已经满足单一主题、上下文完整和可独立引用，所以 CurrentRuleEntryChunking
一条 Entry 生成一个 Chunk；此时再按 512/800 token 切分会破坏语义并制造重复。

只有未来接入 PDF、FAQ、运营手册、产品文档时，才考虑 Structure-Aware 或 Semantic
Chunking。Chunk 太大导致噪声、Token/Latency/Cost 增加；太小导致条件与结论分离、
召回缺上下文；overlap 可以缓解边界切断，但会增加索引体积、重复召回和 Context。

Chunk Size 不能拍脑袋。生产应对 256/512/768/1024 等候选粒度实验，联合比较
Recall@K、MRR、Answer Correctness、Faithfulness、Context Token、Latency 和 Cost。
本项目没有跑这些实验，不能引用虚构最优值。

## 5. BM25 Reference（C）

BM25 使用词频 TF、逆文档频率 IDF、文档长度归一化以及 k1/b：
`IDF(q) * TF*(k1+1)/(TF+k1*(1-b+b*dl/avgdl))`。Reference 默认 k1=1.5、b=0.75，
但参数需要数据集调优。订单号、活动 ID、错误码、状态码和专有名词通常 lexical-heavy，
BM25 的精确词匹配很有价值。当前真实实现不是标准 BM25 库。

## 6. Dense/Embedding Reference（C）

EmbeddingModel 只定义 embed_query/embed_documents；VectorStore 只定义 add/search/delete/
filter，不加载模型或启动服务。Cosine 看方向；dot product 同时受方向和模长影响；L2
看欧氏距离。向量归一化后 cosine 与 dot product 的排序可能等价，未归一化时 dot
product 会偏好大模长。

## 7. Vector DB 选型（C）

| 方案 | 形态/规模 | 持久化与过滤 | 分布式/索引 | 复杂度与适用 |
|---|---|---|---|---|
| FAISS | 本地库，中小到大规模单机 | 持久化需自管，metadata 弱 | 多种 ANN，分布式自建 | 实验、离线索引 |
| Chroma | 本地/轻服务，中小规模 | 内置持久化与基础过滤 | 分布式能力有限 | 原型和开发环境 |
| Milvus | 服务化，大规模 | 强过滤与持久化 | 分布式、多索引 | 大规模生产，运维较重 |
| Qdrant/同类 | 服务化，中大规模 | payload filter 完整 | 集群与 ANN | 生产友好，需服务运维 |

当前只有 15 条规则，线性词法检索足够且可解释；引入任一 Vector DB 都会增加依赖、
部署、同步和治理成本，没有数据规模或语义召回收益证据支持。

## 8. Hybrid Retrieval（C）

参考链路是 `BM25 recall + Dense recall → Merge → Deduplicate → Score Fusion`。
Weighted Fusion 先按各路最大分归一化再加权；因为 BM25 和 cosine 原始尺度不同，不能
直接相加。RRF 使用 `1/(k+rank)`，只依赖排名，对跨 Retriever 分数不可比更稳健。

## 9. Metadata Filter（C）

过滤维度包括 knowledge_type、business_domain、version、tenant、permission_scope、
source_level、active、updated_at。tenant/permission 是权限边界，应尽量 pre-filter，
不能先召回敏感文档再删除。普通业务筛选可以按索引能力选择 pre/post filter，但必须
在 Trace 中记录过滤前后候选数。

## 10. Query Rewrite / Multi-Query / HyDE（C）

QueryRewriteResult 保存 original/rewritten query、extracted_entities 和 constraints。
activityId、outTradeNo、status code 必须原样保留，不能被改写模型“优化”掉。Multi-
Query 用多个表达召回后 merge/dedup。HyDE 先生成假设文档再做 embedding retrieval。
精确 ID 和错误码问题不适合过度 rewrite 或 HyDE。

## 11. Rerank（C）

Retriever 快速大范围召回，Reranker 对少量 query-document 对做更细联合判断。生产
示例可 `Recall Top-20 → Cross Encoder → Top-5`，数字仅用于说明，不是当前参数。
Reference Stub 可注入 scorer，默认词交集只用于确定性测试。

## 12. RAG 故障定位

- 正确答案没有形成 Chunk：CHUNKING_FAILURE。
- Chunk 存在但未入索引：INDEXING_FAILURE。
- 索引存在但 Top-K 没有：RETRIEVAL_FAILURE。
- 被权限/业务过滤移除：FILTER_FAILURE。
- 融合丢失：FUSION_FAILURE。
- Top-K 有但 Rerank 掉了：RERANK_FAILURE。
- 候选未进入 DecisionContext：CONTEXT_ASSEMBLY_FAILURE。
- Context 有正确答案但模型答错：GENERATION_FAILURE。

diagnostics.py 把这些阶段固化为可测试分类，防止把所有问题笼统归为“RAG 不准”。

## 13. Retrieval 与 Answer Eval

RetrievalEvalCase 包含 relevant/forbidden document IDs、expected_top_k、expected_empty。
确定性指标实现 Recall@K、Precision@K、MRR、HitRate@K，NDCG 作为生产扩展指标。

生成质量必须另外评估 Correctness、Faithfulness/Groundedness、Answer Relevance、
Completeness、Unsupported Claim Rate。BLEU/ROUGE 只反映表面文本重合，不能充分衡量
开放式业务答案，也不能证明实例结论来自实时 Evidence。
