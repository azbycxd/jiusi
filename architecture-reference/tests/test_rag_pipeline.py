import unittest
from _support import *
from src.rag.knowledge_entry import KnowledgeEntry
from src.rag.query_rewriter import QueryRewriter
from src.rag.reranker import CrossEncoderReranker
from src.rag.retriever import RetrievalHit
from src.rag.diagnostics import RAGFailureStage,diagnose


class BadRewrite:
    def rewrite(self,query): return "查询活动状态"


class RagPipelineTests(unittest.TestCase):
    def test_query_rewrite_preserves_entity(self):
        result=QueryRewriter(BadRewrite()).rewrite("活动100123为什么不能参加")
        self.assertIn("100123",result.rewritten_query); self.assertEqual(result.extracted_entities["activityId"],"100123")
    def test_multi_query_dedup(self):
        self.assertEqual(len(QueryRewriter().multi_query("拼团规则",("拼团规则",))),1)
    def test_reranker_stub(self):
        a=KnowledgeEntry("a","A","活动规则"); b=KnowledgeEntry("b","B","订单规则")
        result=CrossEncoderReranker().rerank("活动",[RetrievalHit(b,1),RetrievalHit(a,1)])
        self.assertEqual(result[0].hit.document_id,"a")
    def test_diagnostics(self):
        issue=diagnose(answer_in_source=True,answer_in_index=True,answer_in_recall=True,answer_after_rerank=False)
        self.assertEqual(issue.stage,RAGFailureStage.RERANK_FAILURE)


if __name__=="__main__": unittest.main()
