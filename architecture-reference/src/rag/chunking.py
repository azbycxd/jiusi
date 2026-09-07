"""【A 当前真实实现映射】Rule Entry 不切块；文件内另列 C 层策略。"""
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ChunkMetadata:
    document_id: str
    sequence: int = 1
    heading_path: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    metadata: ChunkMetadata


class ChunkingStrategy(Protocol):
    def chunk(self, source) -> list[Chunk]: ...


class CurrentRuleEntryChunking:
    """一条治理 Rule 已是完整语义单元，不做 512/800 token 或 overlap。"""
    def chunk(self, entries):
        return [Chunk(item.knowledge_id, item.content,
                      ChunkMetadata(item.knowledge_id, attributes={"category": item.category}))
                for item in entries]


RuleEntryChunking = CurrentRuleEntryChunking


class SemanticChunkingStrategy:
    """【生产化扩展设计，当前真实项目未实现】按语义边界切 PDF/长文档。"""
    def chunk(self, source):
        raise NotImplementedError("需通过 Recall/Correctness/Token/Latency/Cost 联合实验")


class StructureAwareChunking:
    """【生产化扩展设计，当前真实项目未实现】按标题、段落、表格和 FAQ 结构切分。"""
    def chunk(self, source):
        raise NotImplementedError("需要文档解析与结构元数据")


SemanticChunking = SemanticChunkingStrategy
