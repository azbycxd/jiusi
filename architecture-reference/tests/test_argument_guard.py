"""参数格式与来源严格分开测试。"""
import unittest
from _support import *
from src.harness.argument_guard import ArgumentGuard
from src.harness.capability_guard import GuardViolation
from src.tools.arguments import *

class ArgumentTests(unittest.TestCase):
    def test_normalization_and_non_numeric_order(self):
        self.assertEqual(ArgumentGuard().validate({"outTradeNo": "  order-A  "}, OrderFactsArguments),
                         {"outTradeNo": "order-A"})

    def test_missing_wrong_type_bool_range_extra(self):
        for value in ({}, {"activityId": True}, {"activityId": "7"}, {"activityId": -1},
                      {"activityId": 7, "userId": "x"}):
            with self.subTest(value=value), self.assertRaises(GuardViolation):
                ArgumentGuard().validate(value, ActivityFactsArguments)

    def test_enum_and_format(self):
        field = ArgumentField(str, choices=("CLOSE",), pattern="[A-Z]+")
        self.assertEqual(field.normalize("CLOSE"), "CLOSE")
        for value in ("OPEN", "cl ose", ""):
            with self.assertRaises(ValueError):
                field.normalize(value)

    def test_all_parameter_models(self):
        for contract in (ActivityFactsArguments, EligibilityFactsArguments, JoinableTeamFactsArguments):
            self.assertEqual(contract.from_mapping({"activityId": 7}).activity_id, 7)
        self.assertEqual(RuleSearchArguments.from_mapping({"query": " 标签规则 "}).query, "标签规则")
