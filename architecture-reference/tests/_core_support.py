"""Batch 3A 在线主链的离线 Reference 组装。"""
from _support import *
from src.agent.orchestrator import Orchestrator
from src.context.builder import ContextBuilder
from src.decision.model import ReferenceDecisionModel
from src.gateway.request_gateway import RequestGateway
from src.harness.runtime import HarnessRuntime
from src.memory.session_memory import SessionMemory
from src.memory.task_store import TaskStore
from src.routing.intent_router import CompositeIntentRouter
from src.skills.registry import SkillRegistry
from src.skills.participation_diagnosis.skill import SPEC as PARTICIPATION
from src.skills.order_diagnosis.skill import SPEC as ORDER
from src.skills.joinable_team.skill import SPEC as JOINABLE
from src.skills.rule_qa.skill import SPEC as RULE
from src.tools.rag.search_group_buy_rules_tool import SearchGroupBuyRulesTool
from src.rag.knowledge_entry import KnowledgeEntry


class Retriever:
    def search(self, query):
        return [KnowledgeEntry("r-1", "CLOSE", "CLOSE 是订单关闭状态")]


def core_registry():
    client = ReferenceStub(fixtures())
    tools = [ActivityFactsTool(client), EligibilityFactsTool(client),
             OrderFactsTool(client), JoinableTeamFactsTool(client),
             SearchGroupBuyRulesTool(Retriever())]
    return ToolRegistry(tools)


def skill_registry():
    return SkillRegistry((PARTICIPATION, ORDER, JOINABLE, RULE))


def make_orchestrator(decisions):
    tools = core_registry()
    memory = SessionMemory()
    tasks = TaskStore()
    model = ReferenceDecisionModel(decisions)
    runtime = HarnessRuntime.default(tools)
    orchestrator = Orchestrator(CompositeIntentRouter(), skill_registry(),
                                ContextBuilder(), model, runtime, tools,
                                memory, tasks)
    return orchestrator, model, memory, tasks


def request(message, session="session-core", identity="reference-owner"):
    return RequestGateway().normalize(session, message, identity)
