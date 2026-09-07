import unittest
from _support import *
from src.observability.events import SpanType
from src.observability.trace import TraceRecorder
from src.observability.sanitizer import TelemetrySanitizer
from src.observability.metrics import MetricsCollector
from src.observability.cost import TokenUsage


class ObservabilityTests(unittest.TestCase):
    def test_trace_nesting(self):
        recorder=TraceRecorder(); root=recorder.start_span("t",SpanType.REQUEST)
        child=recorder.start_span("t",SpanType.MODEL_CALL,parent_span_id=root.span_id)
        recorder.end_span(child,duration_ms=4); recorder.end_span(root,duration_ms=6)
        self.assertEqual(recorder.traces["t"].spans[1].parent_span_id,root.span_id)
    def test_sanitizer(self):
        safe=TelemetrySanitizer().sanitize({"api_key":"secret","authenticatedUserId":"u","model":"m"})
        self.assertEqual(safe["api_key"],"[REDACTED]"); self.assertEqual(safe["model"],"m")
    def test_metric_aggregation(self):
        metrics=MetricsCollector(); metrics.increment("tool_calls"); metrics.increment("tool_calls",2)
        metrics.observe("latency_ms",10); metrics.observe("latency_ms",20)
        self.assertEqual(metrics.counter_value("tool_calls"),3); self.assertEqual(metrics.percentile("latency_ms",95),20)
    def test_token_usage_aggregation(self):
        value=TokenUsage(10,2,1,0.1)+TokenUsage(4,3,0,0.2)
        self.assertEqual((value.input_tokens,value.output_tokens,value.cached_tokens),(14,5,1)); self.assertAlmostEqual(value.estimated_cost,.3)


if __name__=="__main__": unittest.main()
