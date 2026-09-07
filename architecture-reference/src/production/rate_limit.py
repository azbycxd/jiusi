"""【生产化扩展设计，当前真实项目未实现】单进程 TokenBucket 与 SlidingWindow Reference。"""
from collections import defaultdict,deque
from dataclasses import dataclass
from time import monotonic


@dataclass
class BucketState:
    tokens:float
    updated_at:float


class TokenBucket:
    def __init__(self,capacity,refill_per_second,clock=monotonic):
        if capacity<=0 or refill_per_second<=0: raise ValueError("限流参数必须为正")
        self.capacity=capacity; self.rate=refill_per_second; self.clock=clock; self.states={}
    def allow(self,key,cost=1):
        now=self.clock(); state=self.states.setdefault(key,BucketState(float(self.capacity),now))
        state.tokens=min(self.capacity,state.tokens+(now-state.updated_at)*self.rate); state.updated_at=now
        if cost<=0 or state.tokens<cost: return False
        state.tokens-=cost; return True


class SlidingWindowCounter:
    def __init__(self,limit,window_seconds,clock=monotonic):
        if limit<1 or window_seconds<=0: raise ValueError("窗口参数非法")
        self.limit=limit; self.window=window_seconds; self.clock=clock; self.events=defaultdict(deque)
    def allow(self,key):
        now=self.clock(); events=self.events[key]
        while events and events[0]<=now-self.window: events.popleft()
        if len(events)>=self.limit: return False
        events.append(now); return True


# 生产需按 user、tenant、provider、skill 与全局多维组合，并使用共享原子存储。
