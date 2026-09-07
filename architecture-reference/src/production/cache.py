"""【生产化扩展设计，当前真实项目未实现】业务缓存、语义缓存和 Prompt Prefix Cache 边界。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticCacheKey:
    user_scope:str|None
    business_id:str|None
    intent:str
    time_bucket:str
    permission_scope:str
    normalized_query:str


class CachePolicy:
    def semantic_cache_allowed(self,*,intent,realtime_facts,user_scoped):
        if realtime_facts or user_scoped: return False
        return intent=="RULE_QA"
    def ttl_seconds(self,*,realtime_facts):
        return 0 if realtime_facts else 300


# 实时订单/资格不能仅凭语义相似命中；Rule QA 更适合缓存。Prefix Cache 只复用稳定
# Prompt 前缀，不改变 Evidence 或身份作用域。
