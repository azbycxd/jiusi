from diagnosis.reason_codes import ReasonCode


REASON_RESPONSES = {
    ReasonCode.ORDER_UNPAID: "该订单尚未完成支付，请先确认支付状态。",
    ReasonCode.GROUP_IN_PROGRESS: "该订单仍在拼团中，暂未达到成团条件，请耐心等待其他成员参团。",
    ReasonCode.GROUP_FULL_BUT_AWAITING_PAYMENT: "拼团人数已满，但仍有成员等待支付完成，请稍后再查看。",
    ReasonCode.GROUP_COMPLETED: "该拼团已成功完成。",
    ReasonCode.GROUP_FAILED: "该拼团未能在活动规则规定时间内成团，请以订单页的后续状态为准。",
    ReasonCode.ORDER_REFUNDED: "该订单已进入退款相关状态，请以订单页展示为准。",
    ReasonCode.NOTIFY_PENDING: "拼团结果已产生，通知正在处理中，请稍后查看订单消息。",
    ReasonCode.NOTIFY_RETRY: "拼团结果通知正在重试，请稍后查看订单消息。",
    ReasonCode.NOTIFY_FAILED: "拼团结果通知发送失败，已建议人工客服协助确认。",
    ReasonCode.ORDER_NOT_FOUND_OR_NOT_AUTHORIZED: "订单不存在，或当前账号无权查看该订单。",
}


def answer_for_reason(reason_code: str) -> str | None:
    try:
        return REASON_RESPONSES.get(ReasonCode(reason_code))
    except ValueError:
        return None
