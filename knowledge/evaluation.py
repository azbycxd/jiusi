from __future__ import annotations

from dataclasses import dataclass

from knowledge.retriever import RuleRetriever


@dataclass(frozen=True)
class RuleRetrievalCase:
    query: str
    expected_knowledge_id: str


RULE_RETRIEVAL_EVAL_SET: tuple[RuleRetrievalCase, ...] = (
    RuleRetrievalCase("拼团的完整支付流程是什么", "group_buy_basic_flow"),
    RuleRetrievalCase("我自己开团和加入别人发起的团有什么不同", "group_buy_start_or_join"),
    RuleRetrievalCase("几个人才算拼团成功", "group_buy_team_complete_rule"),
    RuleRetrievalCase("lockCount和completeCount有什么区别", "group_buy_team_count_semantics"),
    RuleRetrievalCase("团队显示失败或完成分别意味着什么", "group_buy_team_status_semantics"),
    RuleRetrievalCase("订单创建、完成和退单状态该怎么理解", "group_buy_order_status_semantics"),
    RuleRetrievalCase("活动在什么情况下会失效不能参与", "group_buy_activity_validity_rule"),
    RuleRetrievalCase("一个活动可以参加多少次", "group_buy_user_take_limit"),
    RuleRetrievalCase("为什么我可能看不到这个拼团活动", "group_buy_tag_eligibility"),
    RuleRetrievalCase("拼团有哪些优惠方式", "group_buy_discount_types_and_pricing"),
    RuleRetrievalCase("可加入的拼团队伍如何筛选", "group_buy_joinable_team_selection"),
    RuleRetrievalCase("订单超时没付款会怎么样", "group_buy_timeout_unpaid_handling"),
    RuleRetrievalCase("拼团没有成功的已支付订单会怎样退单", "group_buy_unformed_team_refund"),
    RuleRetrievalCase("已经拼团成功后有人退单会影响团队吗", "group_buy_formed_team_refund_impact"),
    RuleRetrievalCase("订单CLOSE是不是说明钱已经退回来了", "group_buy_close_status_semantics"),
    RuleRetrievalCase("支付结算后团队人数怎么变化", "group_buy_team_complete_rule"),
    RuleRetrievalCase("已锁定订单人数和实际付款人数差在哪", "group_buy_team_count_semantics"),
    RuleRetrievalCase("当前活动是否还能参加需要看什么", "group_buy_activity_validity_rule"),
    RuleRetrievalCase("候选拼团队伍为什么可能为空", "group_buy_joinable_team_selection"),
    RuleRetrievalCase("订单CLOSE后支付渠道的钱就到账了吗", "group_buy_close_status_semantics"),
)

IRRELEVANT_RULE_QUERIES: tuple[str, ...] = (
    "今天天气怎么样",
    "帮我写Python排序",
    "股票为什么上涨",
    "附近有什么好吃的",
    "明天几点下雨",
)


@dataclass(frozen=True)
class RuleRetrievalMetrics:
    top1_hit_rate: float
    top3_hit_rate: float


def evaluate_rule_retriever(retriever: RuleRetriever) -> RuleRetrievalMetrics:
    top1_hits = 0
    top3_hits = 0
    for case in RULE_RETRIEVAL_EVAL_SET:
        ids = [item.knowledge_id for item in retriever.search(case.query).results]
        top1_hits += int(bool(ids) and ids[0] == case.expected_knowledge_id)
        top3_hits += int(case.expected_knowledge_id in ids[:3])
    total = len(RULE_RETRIEVAL_EVAL_SET)
    return RuleRetrievalMetrics(top1_hit_rate=top1_hits / total, top3_hit_rate=top3_hits / total)
