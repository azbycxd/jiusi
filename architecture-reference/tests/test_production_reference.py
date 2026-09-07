import unittest
from _support import *
from src.production.rate_limit import TokenBucket,SlidingWindowCounter
from src.production.circuit_breaker import CircuitBreaker,CircuitState
from src.production.checkpoint import Checkpoint,InMemoryCheckpointStore


class Clock:
    def __init__(self): self.now=0.0
    def __call__(self): return self.now


class ProductionReferenceTests(unittest.TestCase):
    def test_token_bucket(self):
        clock=Clock(); bucket=TokenBucket(2,1,clock)
        self.assertTrue(bucket.allow("u")); self.assertTrue(bucket.allow("u")); self.assertFalse(bucket.allow("u"))
        clock.now=1; self.assertTrue(bucket.allow("u"))
    def test_sliding_window(self):
        clock=Clock(); limiter=SlidingWindowCounter(1,10,clock)
        self.assertTrue(limiter.allow("u")); self.assertFalse(limiter.allow("u")); clock.now=11; self.assertTrue(limiter.allow("u"))
    def test_circuit_breaker_transition(self):
        clock=Clock(); breaker=CircuitBreaker(2,10,clock)
        breaker.record_failure(); breaker.record_failure(); self.assertEqual(breaker.state,CircuitState.OPEN); self.assertFalse(breaker.allow_request())
        clock.now=11; self.assertTrue(breaker.allow_request()); self.assertEqual(breaker.state,CircuitState.HALF_OPEN)
        breaker.record_success(); self.assertEqual(breaker.state,CircuitState.CLOSED)
    def test_checkpoint_cas(self):
        store=InMemoryCheckpointStore(); store.save(Checkpoint("t",1,{"x":1}))
        self.assertEqual(store.compare_and_set("t",1,{"x":2}).version,2)
        with self.assertRaises(ValueError): store.compare_and_set("t",1,{"x":3})


if __name__=="__main__": unittest.main()
