"""A 层 候选团队集合 Tool 的 Reference 实现。

由 Registry/Harness 调用；只接收 activityId 业务参数。
公共 AgentTool.run 依次校验参数、提取可信身份、调用 _invoke、验证结果、
映射 timeout/connection/contract 错误；本模块不向模型暴露身份字段。
例如 candidate_teams=[] 是成功事实，不能当查询失败。
"""
from ..base import AgentTool, RepeatPolicy
from ..arguments import JoinableTeamFactsArguments


class JoinableTeamFactsTool(AgentTool):
    """候选团队集合单一动作；Skill 决定它是否属于当前任务。"""

    name = "get_joinable_team_facts"
    description = "候选团队集合"
    arguments_type = JoinableTeamFactsArguments
    result_schema = {"candidate_teams": list}
    dimension = "candidate_teams"
    repeat_policy = RepeatPolicy(repeatable=False, max_same_call=1)
    source = "reference_java_stub"

    def __init__(self, client):
        """注入 JavaMarketClient Protocol；Reference 默认不创建外部连接。"""
        self.client = client

    def _invoke(self, arguments, auth):
        """仅向指定 Client 方法传递规范实体和可信身份上下文。"""
        return self.client.get_joinable_team_facts(arguments.activity_id, auth)

    def validate_result(self, data):
        """公共 JSON 安全校验之后，再检查本业务对象的内部结构。"""
        if isinstance(data, dict) and "candidateTeams" in data:
            if "candidate_teams" in data:
                raise ValueError("候选集合别名重复，不能默选一个版本")
            data = dict(data)
            data["candidate_teams"] = data.pop("candidateTeams")
        result = super().validate_result(data)
        for team in result["candidate_teams"]:
            if not isinstance(team, dict) or not isinstance(team.get("team_id"), str):
                raise ValueError("候选团队缺少 team_id")
        return result
