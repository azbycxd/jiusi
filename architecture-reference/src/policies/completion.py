"""完成判断是信息充分性，不是固定第几个 Tool。"""
from enum import Enum
class Completion(str,Enum): CONTINUE='CONTINUE'; COMPLETE='COMPLETE'; NEED_INPUT='NEED_INPUT'; FAILED='FAILED'
