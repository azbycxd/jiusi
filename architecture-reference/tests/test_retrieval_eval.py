import unittest
from _support import *
from src.eval.case import RetrievalEvalCase
from src.eval.metrics import hit_rate_at_k,precision_at_k,recall_at_k,reciprocal_rank
from src.eval.retrieval_eval import RetrievalEvaluator
from src.rag.knowledge_entry import KnowledgeEntry
from src.rag.retriever import RetrievalHit,RetrievalResult


class RetrievalEvalTests(unittest.TestCase):
    def test_metric_formulas(self):
        ids=("x","a","b"); relevant={"a","c"}
        self.assertEqual(recall_at_k(ids,relevant,2),.5); self.assertEqual(precision_at_k(ids,relevant,2),.5)
        self.assertEqual(reciprocal_rank(ids,relevant),.5); self.assertEqual(hit_rate_at_k(ids,relevant,1),0)
    def test_case_evaluator(self):
        hit=RetrievalHit(KnowledgeEntry("a","A","规则"),1)
        result=RetrievalResult("q",(hit,),3)
        outcome=RetrievalEvaluator().evaluate(RetrievalEvalCase("c","q",frozenset({"a"})),result)
        self.assertTrue(outcome.passed); self.assertEqual(outcome.recall,1)


if __name__=="__main__": unittest.main()
