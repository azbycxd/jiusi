"""HTTP 入口参考；验证请求并把可信身份封装为 RequestContext，不接受 body userId。"""
from .request_context import RequestContext
class RequestGateway:
 def normalize(self,session_id:str,message:str,authenticated_user_id:str)->RequestContext:
  if not session_id or not message.strip() or not authenticated_user_id: raise ValueError('请求或可信身份缺失')
  return RequestContext(session_id,authenticated_user_id,message.strip())
