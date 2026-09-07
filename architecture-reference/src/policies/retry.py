"""Retry 是同一动作的自动重试，不等于模型 Repeat。"""
def may_retry(retry_count,max_retries,retryable): return retryable and retry_count<max_retries
