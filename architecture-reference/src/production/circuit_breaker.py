"""【生产化扩展设计，当前真实项目未实现】下游持续失败时的 Circuit Breaker Reference。"""
from enum import Enum
from time import monotonic


class CircuitState(str,Enum): CLOSED="CLOSED"; OPEN="OPEN"; HALF_OPEN="HALF_OPEN"


class CircuitBreaker:
    def __init__(self,failure_threshold=3,cooldown_seconds=30,clock=monotonic):
        self.threshold=failure_threshold; self.cooldown=cooldown_seconds; self.clock=clock
        self.state=CircuitState.CLOSED; self.failures=0; self.opened_at=None; self.probe_in_flight=False
    def allow_request(self):
        if self.state is CircuitState.OPEN:
            if self.clock()-(self.opened_at or 0)<self.cooldown: return False
            self.state=CircuitState.HALF_OPEN
        if self.state is CircuitState.HALF_OPEN:
            if self.probe_in_flight: return False
            self.probe_in_flight=True
        return True
    def record_success(self):
        self.state=CircuitState.CLOSED; self.failures=0; self.opened_at=None; self.probe_in_flight=False
    def record_failure(self):
        self.probe_in_flight=False; self.failures+=1
        if self.state is CircuitState.HALF_OPEN or self.failures>=self.threshold:
            self.state=CircuitState.OPEN; self.opened_at=self.clock()
