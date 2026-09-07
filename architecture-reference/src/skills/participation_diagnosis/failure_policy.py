"""缺活动号可补参；事实能力不可用才转人工。"""


def decide(missing, unavailable, retryable=False):
    if missing:
        return "REQUEST_INPUT"
    if retryable:
        return "RETRY"
    return "HANDOFF" if unavailable else "CONTINUE"
