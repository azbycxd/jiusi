"""Reference 测试公共夹具：只用内存 Stub，不导入真实应用或外部服务。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.state import AgentState, TaskStatus
from src.skills.base import SkillSpec, KnowledgePolicy
from src.decision.actions import Action
from src.decision.schemas import Decision
from src.tools.java.java_market_client import ReferenceStub
from src.tools.java.activity_facts_tool import ActivityFactsTool
from src.tools.java.eligibility_facts_tool import EligibilityFactsTool
from src.tools.java.order_facts_tool import OrderFactsTool
from src.tools.java.joinable_team_facts_tool import JoinableTeamFactsTool
from src.tools.registry import ToolRegistry
from src.tools.tool_result import ToolResult
from src.observations.observation import ObservationFactory
from src.observations.evidence import EvidenceRegistry
from src.observations.provenance import ParameterProvenance, SourceType
from src.skills.participation_diagnosis.completion_policy import (
    EVIDENCE_OBLIGATIONS, POSSIBLE_DIMENSIONS, resolve_requirements,
)

def make_skill(**budgets):
    """构造明确的参与诊断 Skill，不依赖其它批次未展开的 SPEC 常量。"""
    return SkillSpec(
        name="participation", version="ref", description="参与诊断",
        required_entities=("activityId",),
        allowed_tools=("get_activity_facts", "get_user_eligibility_facts"),
        knowledge_policy=KnowledgePolicy.OPTIONAL, prompt_policy="参考中文指令",
        context_policy="按事实选择", progress_policy="按 Evidence Obligation 更新",
        completion_policy="Required Obligation 满足", failure_policy="有限重试后转人工",
        possible_dimensions=POSSIBLE_DIMENSIONS,
        evidence_obligations=EVIDENCE_OBLIGATIONS,
        requirement_resolver=resolve_requirements,
        runtime_budget={"max_iterations": 8, "max_tool_calls": 5,
                        "max_model_calls": 8, "max_tool_retries": 1,
                        "max_same_call": 1, **budgets})

def make_state(skill=None):
    """测试身份只是参考占位值，不是真实用户。"""
    skill = skill or make_skill()
    state = AgentState("s", "t", "reference-owner", current_query="为什么不能参与")
    state.skill_progress = skill.create_progress(state.current_query)
    state.task_status = TaskStatus.REASONING
    return state

def fixtures():
    """显式 Reference Facts；不声称来自 Java 数据库。"""
    return {
        ("activity", 7): {"data": {"activity": {
            "status": "CLOSED", "within_valid_time": False,
        }}},
        ("eligibility", 7): {"data": {"eligibility": {
            "participation_limit_reached": True,
            "tag_participation_allowed": False,
            "market_downgraded": False,
            "user_within_release_range": True,
        }}},
        ("order", "o-7"): {"owner": "reference-owner",
                         "data": {"order": {"status": "CLOSE"}, "references": {"activity_id": 7}}},
        ("joinable", 7): {"data": {"candidate_teams": []}},
    }

def make_registry(client=None):
    """四个离线事实工具共享同一可观察 Stub。"""
    client = client or ReferenceStub(fixtures())
    return ToolRegistry([ActivityFactsTool(client), EligibilityFactsTool(client),
                         OrderFactsTool(client), JoinableTeamFactsTool(client)])

def observation(data=None, name="get_activity_facts"):
    """通过真实 Reference 工厂生成 Evidence，禁止手工伪造成功路径。"""
    data = {"activity": {"status": "CLOSED", "within_valid_time": False}} if data is None else data
    return ObservationFactory().create(ToolResult.success_result(name, data))

def provenance(value=7):
    """可信账本由测试 Runtime 提供，不来自 Decision 字段。"""
    return [ParameterProvenance("activityId", value, SourceType.USER_INPUT, "activityId")]
