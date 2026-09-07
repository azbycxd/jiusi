import unittest
from _support import *
from src.rag.knowledge_entry import KnowledgeEntry
from src.rag.bm25_retriever import BM25Retriever
from src.rag.lexical_retriever import LexicalRetriever
from src.rag.hybrid_retriever import HybridRetriever
from src.rag.metadata_filter import MetadataFilter
from src.rag.retriever import RetrievalHit,RetrievalResult


def entries():
    return [KnowledgeEntry("r1","CLOSE 状态","订单关闭后的拼团规则",category="order",tags=("CLOSE",),internal_metadata={"tenant":"t1","active":True}),
            KnowledgeEntry("r2","活动限制","活动参与次数限制",category="activity",tags=("参与限制",),internal_metadata={"tenant":"t1","active":True}),
            KnowledgeEntry("r3","无关","配送规则",category="shipping",internal_metadata={"tenant":"t2","active":True})]


class FixedRetriever:
    def __init__(self,hits): self.hits=hits
    def search_with_scores(self,query,top_k=3): return RetrievalResult(query,tuple(self.hits[:top_k]),top_k)


class RagRetrievalTests(unittest.TestCase):
    def test_bm25_basic(self):
        result=BM25Retriever(entries()).search_with_scores("CLOSE 订单",top_k=2)
        self.assertEqual(result.hits[0].document_id,"r1"); self.assertGreater(result.hits[0].score,0)
    def test_lexical_breakdown_and_empty(self):
        retriever=LexicalRetriever(entries())
        self.assertEqual(retriever.search_with_scores("天气预报晴天").hits,())
        self.assertIn("title_overlap",retriever.search_with_scores("CLOSE 状态").hits[0].score_breakdown)
    def test_hybrid_rrf_and_dedup(self):
        e=entries(); a=[RetrievalHit(e[0],8),RetrievalHit(e[1],3)]; b=[RetrievalHit(e[1],.9),RetrievalHit(e[0],.8)]
        result=HybridRetriever({"bm25":FixedRetriever(a),"dense":FixedRetriever(b)},fusion="rrf").search_with_scores("q")
        self.assertEqual(len(result.hits),2); self.assertEqual({h.document_id for h in result.hits},{"r1","r2"})
    def test_hybrid_weighted(self):
        e=entries(); result=HybridRetriever({"a":FixedRetriever([RetrievalHit(e[0],10)]),"b":FixedRetriever([RetrievalHit(e[1],.2)])},fusion="weighted").search_with_scores("q")
        self.assertEqual(len(result.hits),2)
    def test_metadata_filter(self):
        filtered=MetadataFilter(tenant="t1").prefilter(entries())
        self.assertEqual({e.knowledge_id for e in filtered},{"r1","r2"})


if __name__=="__main__": unittest.main()
