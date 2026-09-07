"""【B 架构重构】进程内 Counter/Histogram/Gauge Reference。"""
from collections import defaultdict


CORE_COUNTERS=("task_total","task_success","task_handoff","model_calls","model_failures",
               "tool_calls","tool_failures","tool_retries","model_retries",
               "evidence_failures","retrieval_hits")


class MetricsCollector:
    def __init__(self):
        self.counters=defaultdict(int); self.histograms=defaultdict(list); self.gauges={}; self.latencies=[]

    @staticmethod
    def _key(name,labels=None): return (name,tuple(sorted((labels or {}).items())))
    def increment(self,name,amount=1,labels=None): self.counters[self._key(name,labels)]+=amount
    def observe(self,name,value,labels=None): self.histograms[self._key(name,labels)].append(float(value))
    def set_gauge(self,name,value,labels=None): self.gauges[self._key(name,labels)]=float(value)
    def counter_value(self,name,labels=None): return self.counters[self._key(name,labels)]
    def histogram_values(self,name,labels=None): return tuple(self.histograms[self._key(name,labels)])
    def observe_latency(self,ms): self.latencies.append(ms); self.observe("latency_ms",ms)
    def increment_tool_call(self): self.increment("tool_calls")
    def increment_model_call(self): self.increment("model_calls")
    def record_handoff(self): self.increment("task_handoff")
    def record_evidence_failure(self): self.increment("evidence_failures")

    def percentile(self,name,percentile,labels=None):
        values=sorted(self.histogram_values(name,labels))
        if not values: return None
        index=max(0,min(len(values)-1,round((percentile/100)*(len(values)-1))))
        return values[index]
