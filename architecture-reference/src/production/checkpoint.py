"""【生产化扩展设计，当前真实项目未实现】Checkpoint CAS；Checkpoint 不等于 Long-Term Memory。"""
from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Checkpoint:
    task_id:str
    version:int
    state:object


class CheckpointStore(Protocol):
    def save(self,checkpoint:Checkpoint): ...
    def load(self,task_id:str)->Checkpoint|None: ...
    def compare_and_set(self,task_id:str,expected_version:int,state)->Checkpoint: ...


class InMemoryCheckpointStore:
    def __init__(self): self.values={}
    def save(self,checkpoint):
        if checkpoint.task_id in self.values: raise ValueError("CHECKPOINT_EXISTS")
        self.values[checkpoint.task_id]=deepcopy(checkpoint); return deepcopy(checkpoint)
    def load(self,task_id): return deepcopy(self.values.get(task_id))
    def compare_and_set(self,task_id,expected_version,state):
        current=self.values.get(task_id)
        if current is None or current.version!=expected_version: raise ValueError("CHECKPOINT_VERSION_CONFLICT")
        updated=Checkpoint(task_id,expected_version+1,deepcopy(state)); self.values[task_id]=updated; return deepcopy(updated)


class RedisCheckpointStore:
    """Stub：生产需原子 Lua/事务、TTL、序列化版本与多实例验证。"""
    def save(self,checkpoint): raise NotImplementedError
    def load(self,task_id): raise NotImplementedError
    def compare_and_set(self,task_id,expected_version,state): raise NotImplementedError
