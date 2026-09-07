def decide(missing, unavailable, retryable=False):
    if retryable:
        return "RETRY"
    return "HANDOFF" if unavailable else "CONTINUE"
