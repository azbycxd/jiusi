"""保护模型参数与可信身份两个入口。"""
import unittest
from _support import *
from src.harness.identity_guard import IdentityGuard
from src.harness.capability_guard import GuardViolation

class IdentityTests(unittest.TestCase):
    def test_protected_aliases_and_nested(self):
        for key in ("userId", "authenticated_user_id", "TOKEN", "header", "SQL", "redisKey", "baseUrl"):
            with self.subTest(key=key), self.assertRaises(GuardViolation):
                IdentityGuard().validate_model_arguments({"nested": [{key: "value"}]})

    def test_auth_from_state_only(self):
        auth = IdentityGuard().build_auth_context(make_state())
        self.assertEqual(auth.authenticated_user_id, "reference-owner")
        self.assertNotIn("reference-owner", repr(auth))
        with self.assertRaises(GuardViolation):
            IdentityGuard().build_auth_context({"authenticated_user_id": "untrusted"})
