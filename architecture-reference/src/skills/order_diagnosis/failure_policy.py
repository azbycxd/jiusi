def decide(missing, unavailable, retryable=False):
    if missing:
        return "REQUEST_INPUT"
    if retryable:
        return "RETRY"
    return "HANDOFF" if unavailable else "CONTINUE"
