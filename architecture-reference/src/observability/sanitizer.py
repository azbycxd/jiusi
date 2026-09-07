"""【B 架构重构】Telemetry 脱敏；Trace 只保留安全摘要。"""
import re
from ..observations.observation import normalize_key


class TelemetrySanitizer:
    FORBIDDEN={"apikey","token","authorization","header","headers","userid",
               "authenticateduserid","sql","javastack","stacktrace","prompt",
               "providerrawresponse","secret","password"}

    def sanitize(self,value,key=None):
        if key is not None and normalize_key(key) in self.FORBIDDEN:
            return "[REDACTED]"
        if isinstance(value,dict):
            return {str(name):self.sanitize(item,str(name)) for name,item in value.items()}
        if isinstance(value,(list,tuple)):
            return [self.sanitize(item) for item in value]
        if isinstance(value,str):
            if re.search(r"(?i)bearer\s+[A-Za-z0-9._-]+",value): return "[REDACTED]"
            if len(value)>500: return value[:200]+"…[TRUNCATED]"
        return value
