"""失败策略：用户可补→REQUEST_INPUT，能力不足/不可用→HANDOFF。"""
def decide_failure(error_code,retryable): return 'RETRY' if retryable else 'HANDOFF'
