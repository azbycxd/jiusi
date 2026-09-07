import unittest
from _support import *
from src.eval.failure_classifier import FailureClassifier,FailureKind


class FailureClassifierTests(unittest.TestCase):
    def test_explicit_error_category(self):
        self.assertEqual(FailureClassifier().classify(error_code="EVIDENCE_NOT_AVAILABLE"),FailureKind.EVIDENCE_FAILURE)
        self.assertEqual(FailureClassifier().classify(error_code="INVALID_ARGUMENT"),FailureKind.TOOL_ARGUMENT_FAILURE)
    def test_span_and_infra(self):
        self.assertEqual(FailureClassifier().classify(span_type="ROUTING"),FailureKind.ROUTING_FAILURE)
        self.assertEqual(FailureClassifier().classify(infra=True),FailureKind.INFRA_FAILURE)


if __name__=="__main__": unittest.main()
