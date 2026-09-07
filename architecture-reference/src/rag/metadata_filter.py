"""【生产化扩展设计，当前真实项目未实现】召回前权限 Filter 与普通业务 Filter。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MetadataFilter:
    knowledge_type: str | None = None
    business_domain: str | None = None
    version: str | None = None
    tenant: str | None = None
    permission_scope: str | None = None
    source_level: str | None = None
    active: bool | None = True
    updated_after: str | None = None

    def matches(self, metadata):
        checks = {
            "knowledge_type": self.knowledge_type,
            "business_domain": self.business_domain,
            "version": self.version,
            "tenant": self.tenant,
            "permission_scope": self.permission_scope,
            "source_level": self.source_level,
            "active": self.active,
        }
        if any(expected is not None and metadata.get(name) != expected
               for name, expected in checks.items()):
            return False
        return not self.updated_after or metadata.get("updated_at", "") >= self.updated_after

    def prefilter(self, entries):
        """tenant/permission_scope 应尽量在召回前执行，不能先泄露再删除。"""
        return [entry for entry in entries if self.matches({
            **entry.governance_view(), "source_level": entry.source_level,
            "version": entry.version,
        })]
