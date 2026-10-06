#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  tests/unknown.py
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are
#  met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following disclaimer
#    in the documentation and/or other materials provided with the
#    distribution.
#  * Neither the name of the project nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
#  "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
#  LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
#  A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
#  OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
#  SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
#  LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
#  OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""未知值（三值逻辑）语义测试。"""

import pickle
import threading
import unittest

import rule_engine.engine as engine
import rule_engine.errors as errors
import rule_engine.types as types
from rule_engine import (
        Rule,
        UnknownAbortError,
        UnknownAction,
        UnknownFieldError,
        UnknownPolicy,
        UnknownReason,
        UnknownValue,
)

__all__ = ('UnknownValueTests', 'UnknownPolicyTests', 'UnknownTruthTableTests', 'UnknownEvaluationTests')

PROPAGATE = UnknownPolicy.propagate_all()


class UnknownValueTests(unittest.TestCase):
    def test_reasons_and_construction(self):
        unknown = UnknownValue(UnknownReason.MISSING, source=('person', 'age'), detail='not submitted')
        self.assertIs(unknown.reason, UnknownReason.MISSING)
        self.assertEqual(unknown.source, ('person', 'age'))
        self.assertEqual(unknown.detail, 'not submitted')

    def test_reason_coerced_from_string(self):
        self.assertIs(UnknownValue('masked').reason, UnknownReason.MASKED)
        self.assertIs(UnknownValue('parse_error').reason, UnknownReason.PARSE_ERROR)

    def test_immutable(self):
        unknown = UnknownValue(UnknownReason.MISSING, source=('a',))
        with self.assertRaises(AttributeError):
            unknown.reason = UnknownReason.MASKED  # type: ignore[misc]

    def test_no_silent_bool_coercion(self):
        unknown = UnknownValue(UnknownReason.MISSING)
        with self.assertRaises(TypeError):
            bool(unknown)
        self.assertTrue(unknown) if False else None

    def test_derive_appends_path(self):
        unknown = UnknownValue(UnknownReason.MISSING, source=('age',))
        derived = unknown.derive('person', None)
        self.assertEqual(derived.source, ('age', 'person'))
        self.assertIs(derived.reason, UnknownReason.MISSING)
        # 原始未知值不被修改
        self.assertEqual(unknown.source, ('age',))

    def test_explain_contains_no_value(self):
        unknown = UnknownValue(UnknownReason.PARSE_ERROR, source=('dob',), detail='unparseable')
        self.assertEqual(unknown.explain(), {'reason': 'parse_error', 'source': 'dob', 'detail': 'unparseable'})

    def test_equality_and_hash(self):
        a = UnknownValue(UnknownReason.MISSING, source=('x',))
        b = UnknownValue(UnknownReason.MISSING, source=('x',))
        c = UnknownValue(UnknownReason.MASKED, source=('x',))
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertNotEqual(a, c)
        self.assertNotEqual(a, False)

    def test_from_error(self):
        error = UnknownFieldError(UnknownReason.MASKED, 'blocked', source=('salary',))
        unknown = UnknownValue.from_error(error)
        self.assertIs(unknown.reason, UnknownReason.MASKED)
        self.assertEqual(unknown.source, ('salary',))

class UnknownPolicyTests(unittest.TestCase):
    def test_propagate_preset(self):
        policy = UnknownPolicy.propagate_all()
        unknown = UnknownValue(UnknownReason.MISSING)
        self.assertIs(policy.resolve(unknown), unknown)

    def test_abort_preset(self):
        policy = UnknownPolicy.abort_all()
        with self.assertRaises(UnknownAbortError):
            policy.resolve(UnknownValue(UnknownReason.PARSE_ERROR, source=('x',)))

    def test_binary_preset(self):
        policy = UnknownPolicy.binary(False)
        self.assertIs(policy.resolve(UnknownValue(UnknownReason.MISSING)), False)
        self.assertIs(policy.resolve(UnknownValue(UnknownReason.MASKED)), False)

    def test_per_reason_independent_actions(self):
        policy = UnknownPolicy(
                missing=(UnknownAction.DEFAULT, 0),
                parse_error=UnknownAction.ABORT,
                masked=UnknownAction.PROPAGATE
        )
        self.assertEqual(policy.resolve(UnknownValue(UnknownReason.MISSING)), 0)
        masked = UnknownValue(UnknownReason.MASKED)
        self.assertIs(policy.resolve(masked), masked)
        with self.assertRaises(UnknownAbortError):
            policy.resolve(UnknownValue(UnknownReason.PARSE_ERROR))

    def test_default_requires_fallback(self):
        with self.assertRaises(ValueError):
            UnknownPolicy(missing=UnknownAction.DEFAULT)

    def test_fallback_requires_default_action(self):
        with self.assertRaises(ValueError):
            UnknownPolicy(missing=(UnknownAction.PROPAGATE, 1))

    def test_abort_error_preserves_source_without_value(self):
        policy = UnknownPolicy.abort_all()
        try:
            policy.resolve(UnknownValue(UnknownReason.MASKED, source=('person', 'ssn')))
        except UnknownAbortError as error:
            self.assertIn('person.ssn', error.message)
            self.assertEqual(error.unknown.source, ('person', 'ssn'))
            self.assertIs(error.unknown.reason, UnknownReason.MASKED)
        else:
            self.fail('UnknownAbortError was not raised')

    def test_context_pickle_roundtrip(self):
        policy = UnknownPolicy(missing=(UnknownAction.DEFAULT, False), parse_error=UnknownAction.ABORT)
        context = engine.Context(unknown_policy=policy)
        restored = pickle.loads(pickle.dumps(context))
        self.assertEqual(restored.unknown_policy, policy)

    def test_context_pickle_without_policy_stays_binary(self):
        context = engine.Context()
        restored = pickle.loads(pickle.dumps(context))
        self.assertIsNone(restored.unknown_policy)

class UnknownTruthTableTests(unittest.TestCase):
    """三值真值表：未知记为 U，真 T，假 F。"""
    U = UnknownValue(UnknownReason.MISSING, source=('u',))

    def test_and_table(self):
        from rule_engine.unknown import logic_and
        u = self.U
        self.assertIs(logic_and(True, True), True)
        self.assertIs(logic_and(True, False), False)
        self.assertIs(logic_and(False, True), False)
        self.assertIs(logic_and(False, False), False)
        # F 与 U 得 F（假压制未知）
        self.assertIs(logic_and(False, u), False)
        self.assertIs(logic_and(u, False), False)
        # T 与 U 得 U
        self.assertIs(logic_and(True, u), u)
        self.assertIs(logic_and(u, True), u)
        self.assertIs(logic_and(u, u), u)

    def test_or_table(self):
        from rule_engine.unknown import logic_or
        u = self.U
        self.assertIs(logic_or(False, False), False)
        self.assertIs(logic_or(True, False), True)
        self.assertIs(logic_or(False, True), True)
        # T 与 U 得 T（真压制未知）
        self.assertIs(logic_or(True, u), True)
        self.assertIs(logic_or(u, True), True)
        # F 与 U 得 U
        self.assertIs(logic_or(u, False), u)
        self.assertIs(logic_or(u, u), u)

    def test_not_table(self):
        from rule_engine.unknown import logic_not
        self.assertIs(logic_not(True), False)
        self.assertIs(logic_not(False), True)
        self.assertIs(logic_not(self.U), self.U)

class UnknownEvaluationTests(unittest.TestCase):
    def _context(self, **types_):
        return engine.Context(unknown_policy=PROPAGATE, type_resolver=types_)

    def _untyped_context(self):
        # 不提供 type_resolver：符号在解析期类型未知，与“资料即字典”的资格服务接入方式一致
        return engine.Context(unknown_policy=PROPAGATE)

    # —— 向后兼容：默认上下文仍是纯二值 ——
    def test_default_context_missing_symbol_raises(self):
        rule = Rule('age >= 18')
        with self.assertRaises(errors.SymbolResolutionError):
            rule.evaluate({})

    def test_default_context_matches_is_plain_bool(self):
        rule = Rule('name == "Luke"')
        self.assertIsInstance(rule.matches({'name': 'Luke'}), bool)
        self.assertTrue(rule.matches({'name': 'Luke'}))

    # —— 三态结论 ——
    def test_evaluate_ternary_true_false_unknown(self):
        context = self._context(age=types.DataType.FLOAT)
        rule = Rule('age >= 18', context=context)
        self.assertEqual(rule.evaluate_ternary({'age': 21}).match, True)
        self.assertEqual(rule.evaluate_ternary({'age': 5}).match, False)
        result = rule.evaluate_ternary({})
        self.assertIsNone(result.match)
        self.assertEqual(result.unknowns[0].reason, UnknownReason.MISSING)
        self.assertEqual(result.unknowns[0].source, ('age',))

    def test_matches_collapses_unknown_to_false(self):
        context = self._context(age=types.DataType.FLOAT)
        rule = Rule('age >= 18', context=context)
        # 二值出口保持 bool，未知被压成 False
        self.assertFalse(rule.matches({}))

    # —— 三种原因 ——
    def test_missing_reason(self):
        context = self._context(age=types.DataType.FLOAT)
        result = Rule('age >= 18', context=context).evaluate_ternary({})
        self.assertEqual(result.unknowns[0].reason, UnknownReason.MISSING)

    def test_parse_error_reason_on_type_mismatch(self):
        context = self._context(age=types.DataType.FLOAT)
        result = Rule('age >= 18', context=context).evaluate_ternary({'age': 'not a number'})
        self.assertIsNone(result.match)
        self.assertEqual(result.unknowns[0].reason, UnknownReason.PARSE_ERROR)
        self.assertEqual(result.unknowns[0].source, ('age',))

    def test_parse_error_reason_without_type_hints(self):
        # 无类型上下文：类型不匹配在运算节点才暴露，同样归因为字段解析失败
        context = self._untyped_context()
        result = Rule('age >= 18', context=context).evaluate_ternary({'age': '25?'})
        self.assertIsNone(result.match)
        unknown = result.unknowns[0]
        self.assertEqual(unknown.reason, UnknownReason.PARSE_ERROR)
        self.assertEqual(unknown.source, ('age',))
        # detail 只描述类型问题，不含字段实际内容
        self.assertNotIn('25?', unknown.detail or '')

    def test_parse_error_from_arithmetic_node(self):
        context = self._untyped_context()
        result = Rule('age + 1 > 18', context=context).evaluate_ternary({'age': 'unknown'})
        self.assertIsNone(result.match)
        self.assertEqual(result.unknowns[0].reason, UnknownReason.PARSE_ERROR)
        self.assertEqual(result.unknowns[0].source, ('age',))

    def test_parse_error_default_action_at_operation_node(self):
        context = engine.Context(
                unknown_policy=UnknownPolicy(parse_error=(UnknownAction.DEFAULT, False)),
        )
        # 兜底发生在运算节点，整个比较表达式得到明确 False
        rule = Rule('age >= 18', context=context)
        self.assertFalse(rule.matches({'age': 'bad'}))
        self.assertEqual(rule.evaluate_ternary({'age': 'bad'}).match, False)

    def test_literal_type_error_still_raises_at_parse_time(self):
        # 全字面量的类型错误无法归因到数据字段，维持解析期报错
        context = self._untyped_context()
        with self.assertRaises(errors.EvaluationError):
            Rule('1 + "x"', context=context)

    def test_masked_reason_via_resolver(self):
        def resolver(thing, name):
            if name == 'ssn':
                return UnknownValue(UnknownReason.MASKED, source=('ssn',))
            return thing[name]
        context = engine.Context(unknown_policy=PROPAGATE, resolver=resolver)
        result = Rule('ssn == "123"', context=context).evaluate_ternary({})
        self.assertIsNone(result.match)
        self.assertEqual(result.explain(), [{'reason': 'masked', 'source': 'ssn', 'detail': None}])

    def test_masked_reason_via_custom_function(self):
        def salary_band():
            raise UnknownFieldError(UnknownReason.MASKED, 'not visible', source=('salary_band',))
        def resolver(thing, name):
            if name == 'salary_band':
                return salary_band
            return thing[name]
        context = engine.Context(unknown_policy=PROPAGATE, resolver=resolver)
        result = Rule('salary_band() >= 3', context=context).evaluate_ternary({})
        self.assertIsNone(result.match)
        self.assertEqual(result.unknowns[0].reason, UnknownReason.MASKED)
        self.assertEqual(result.unknowns[0].source, ('salary_band',))

    def test_custom_function_unknown_unknown_without_policy_raises(self):
        def salary_band():
            raise UnknownFieldError(UnknownReason.MASKED, 'not visible')
        def resolver(thing, name):
            if name == 'salary_band':
                return salary_band
            return thing[name]
        context = engine.Context(resolver=resolver)
        with self.assertRaises(UnknownFieldError):
            Rule('salary_band() >= 3', context=context).evaluate({})

    # —— 动作：传播 / 兜底 / 中止 ——
    def test_action_default_for_boolean_leaf(self):
        context = engine.Context(unknown_policy=UnknownPolicy.binary(False))
        rule = Rule('has_documents == true', context=context)
        self.assertFalse(rule.matches({}))

    def test_action_default_numeric_fallback_is_coerced(self):
        context = engine.Context(
                unknown_policy=UnknownPolicy(missing=(UnknownAction.DEFAULT, 0)),
                type_resolver={'age': types.DataType.FLOAT}
        )
        rule = Rule('age >= 18', context=context)
        # int 兜底值在符号点被强转为 Decimal，比较正常，得到明确 False 而非类型错误
        self.assertFalse(rule.matches({}))
        self.assertEqual(rule.evaluate_ternary({}).match, False)

    def test_action_abort(self):
        context = engine.Context(unknown_policy=UnknownPolicy.abort_all())
        rule = Rule('age >= 18', context=context)
        with self.assertRaises(UnknownAbortError) as catcher:
            rule.evaluate({})
        self.assertEqual(catcher.exception.unknown.reason, UnknownReason.MISSING)

    def test_action_abort_only_parse_error(self):
        context = engine.Context(
                unknown_policy=UnknownPolicy(missing=UnknownAction.PROPAGATE, parse_error=UnknownAction.ABORT),
                type_resolver={'age': types.DataType.FLOAT}
        )
        rule = Rule('age >= 18', context=context)
        # 缺失仍传播
        self.assertIsNone(rule.evaluate_ternary({}).match)
        # 解析失败中止
        with self.assertRaises(UnknownAbortError):
            rule.evaluate({'age': object()})

    # —— 布尔短路 ——
    def test_and_short_circuits_on_definite_false(self):
        seen = []
        def resolver(thing, name):
            seen.append(name)
            return thing[name]
        context = engine.Context(
                unknown_policy=PROPAGATE,
                resolver=resolver,
                type_resolver={'a': types.DataType.BOOLEAN, 'b': types.DataType.BOOLEAN}
        )
        Rule('a == true and b == true', context=context).evaluate({'a': False})
        self.assertNotIn('b', seen)

    def test_and_false_dominates_unknown(self):
        context = self._context(age=types.DataType.FLOAT, vip=types.DataType.BOOLEAN)
        rule = Rule('age > 100 and vip == true', context=context)
        # 左侧明确为假，vip 缺失：结论仍明确为假
        self.assertEqual(rule.evaluate_ternary({'age': 5}).match, False)

    def test_or_true_dominates_unknown(self):
        context = self._context(age=types.DataType.FLOAT, vip=types.DataType.BOOLEAN)
        rule = Rule('age >= 18 or vip == true', context=context)
        self.assertEqual(rule.evaluate_ternary({'age': 21}).match, True)

    def test_or_unknown_when_neither_satisfied(self):
        context = self._context(age=types.DataType.FLOAT, vip=types.DataType.BOOLEAN)
        rule = Rule('age >= 18 or vip == true', context=context)
        result = rule.evaluate_ternary({'age': 5})
        self.assertIsNone(result.match)
        self.assertEqual(result.unknowns[0].source, ('vip',))

    def test_not_preserves_unknown(self):
        context = self._context(vip=types.DataType.BOOLEAN)
        self.assertIsNone(Rule('not vip == true', context=context).evaluate_ternary({}).match)

    # —— 比较 ——
    def test_equality_propagates_unknown(self):
        context = self._context(name=types.DataType.STRING)
        for expression in ('name == "Luke"', 'name != "Luke"'):
            self.assertIsNone(Rule(expression, context=context).evaluate_ternary({}).match)

    def test_ordered_comparison_propagates_unknown(self):
        context = self._context(age=types.DataType.FLOAT)
        for expression in ('age > 18', 'age >= 18', 'age < 18', 'age <= 18'):
            self.assertIsNone(Rule(expression, context=context).evaluate_ternary({}).match)

    def test_explicit_null_is_not_unknown(self):
        context = self._context(age=types.DataType.NULLABLE(types.DataType.FLOAT))
        # 明确的 null 与 null 相等：这是确定结论，不是未知
        self.assertTrue(Rule('age == null', context=context).matches({'age': None}))
        self.assertFalse(Rule('age != null', context=context).matches({'age': None}))

    def test_regex_comparison_propagates_unknown(self):
        context = self._context(name=types.DataType.STRING)
        self.assertIsNone(Rule('name =~ "L.*"', context=context).evaluate_ternary({}).match)

    def test_arithmetic_propagates_unknown(self):
        context = self._context(age=types.DataType.FLOAT)
        for expression in ('age + 1 > 18', 'age * 2 > 18', 'age - 1 > 18'):
            self.assertIsNone(Rule(expression, context=context).evaluate_ternary({}).match)

    def test_membership_propagates_unknown(self):
        context = self._context(name=types.DataType.STRING)
        self.assertIsNone(Rule('name in ["Luke", "Yoda"]', context=context).evaluate_ternary({}).match)
        context2 = self._context(names=types.DataType.ARRAY(types.DataType.STRING), name=types.DataType.STRING)
        self.assertIsNone(Rule('name in names', context=context2).evaluate_ternary({}).match)

    # —— 三元 ——
    def test_ternary_unknown_condition_skips_branches(self):
        context = self._context(flag=types.DataType.BOOLEAN)
        result = Rule('flag ? 1 : 2', context=context).evaluate_ternary({})
        self.assertIsNone(result.match)

    # —— 默认值运算 ?? ——
    def test_coalesce_discharges_unknown(self):
        context = self._context(age=types.DataType.FLOAT)
        rule = Rule('(age ?? 0) >= 18', context=context)
        self.assertFalse(rule.matches({}))
        self.assertTrue(rule.matches({'age': 21}))

    def test_coalesce_keeps_known_value(self):
        context = self._context(age=types.DataType.FLOAT)
        rule = Rule('(age ?? 0) >= 18', context=context)
        self.assertTrue(rule.matches({'age': 99}))

    # —— 映射 / 安全导航 ——
    def test_mapping_missing_key_is_unknown(self):
        context = self._untyped_context()
        result = Rule('facts["score"] >= 50', context=context).evaluate_ternary({'facts': {'other': 1}})
        self.assertIsNone(result.match)
        self.assertEqual(result.unknowns[0].reason, UnknownReason.MISSING)
        self.assertEqual(result.unknowns[0].source, ('score',))

    def test_safe_navigation_chain_preserves_source(self):
        context = self._untyped_context()
        result = Rule('person&["profile"]&["level"] >= 3', context=context).evaluate_ternary({'person': {}})
        self.assertIsNone(result.match)
        # 来源沿访问链累积
        self.assertEqual(result.unknowns[0].source, ('profile', 'level'))

    def test_safe_navigation_without_policy_returns_null(self):
        # 无策略时安全导航维持历史语义：缺键返回 null，再经 ?? 兜底
        context = engine.Context()
        rule = Rule('(person&["profile"]&["level"] ?? 0) >= 3', context=context)
        self.assertFalse(rule.matches({'person': {}}))

    # —— 集合推导 ——
    def _people_context(self, nullable_age=False):
        age_type = types.DataType.NULLABLE(types.DataType.FLOAT) if nullable_age else types.DataType.FLOAT
        # 资格资料以字典数组到达：成员是 STRING→FLOAT 的映射，缺失键在运行时被识别为未知
        return self._context(people=types.DataType.ARRAY(types.DataType.MAPPING(types.DataType.STRING, age_type)))

    def test_comprehension_keeps_unknown_members(self):
        context = self._people_context()
        rule = Rule('[p["age"] for p in people]', context=context)
        result = rule.evaluate({'people': ({'age': 20}, {})})
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[1], UnknownValue)
        self.assertEqual(result[1].source, ('age',))

    def test_comprehension_condition_unknown_excludes_member(self):
        context = self._people_context()
        rule = Rule('$all([p["age"] >= 18 for p in people if p["age"] >= 0])', context=context)
        # 第二行条件未知 → 该行被排除；其余行全部满足 → 明确为真
        self.assertTrue(rule.matches({'people': ({'age': 20}, {})}))

    def test_builtin_any_kleene(self):
        context = self._people_context()
        data = {'people': ({'age': 20}, {})}
        rule = Rule('$any([p["age"] >= 18 for p in people])', context=context)
        # 一个明确为真 → 真（即使另一个未知）
        self.assertTrue(rule.matches(data))
        rule2 = Rule('$any([p["age"] >= 100 for p in people])', context=context)
        # 无真但有未知 → 未知
        self.assertIsNone(rule2.evaluate_ternary(data).match)

    def test_builtin_all_kleene(self):
        context = self._people_context()
        data = {'people': ({'age': 20}, {})}
        rule = Rule('$all([p["age"] >= 18 for p in people])', context=context)
        # 无假但有未知 → 未知
        self.assertIsNone(rule.evaluate_ternary(data).match)
        rule2 = Rule('$all([p["age"] >= 100 for p in people])', context=context)
        # 有明确为假 → 假
        self.assertFalse(rule2.matches(data))

    def test_builtin_any_all_empty_are_definite(self):
        context = self._people_context()
        self.assertTrue(Rule('$all([p["age"] for p in people])', context=context).matches({'people': ()}))
        self.assertFalse(Rule('$any([p["age"] for p in people])', context=context).matches({'people': ()}))

    def test_builtin_sum_min_max_propagate_unknown(self):
        context = self._people_context()
        data = {'people': ({'age': 20}, {})}
        self.assertIsNone(Rule('$sum([p["age"] for p in people]) > 100', context=context).evaluate_ternary(data).match)
        self.assertIsNone(Rule('$min([p["age"] for p in people]) == 20', context=context).evaluate_ternary(data).match)
        self.assertIsNone(Rule('$max([p["age"] for p in people]) == 20', context=context).evaluate_ternary(data).match)

    def test_builtin_aggregates_definite_when_complete(self):
        context = self._people_context()
        data = {'people': ({'age': 20}, {'age': 30})}
        self.assertTrue(Rule('$sum([p["age"] for p in people]) == 50', context=context).matches(data))
        self.assertTrue(Rule('$min([p["age"] for p in people]) == 20', context=context).matches(data))
        self.assertTrue(Rule('$max([p["age"] for p in people]) == 30', context=context).matches(data))

    # —— 来源追踪与脱敏 ——
    def test_source_does_not_leak_field_value(self):
        context = self._context(ssn=types.DataType.STRING)
        result = Rule('ssn == "x"', context=context).evaluate_ternary({})
        for explanation in result.explain():
            self.assertNotIn(str({'ssn': 'secret-value'}), str(explanation))
            self.assertEqual(set(explanation.keys()), {'reason', 'source', 'detail'})

    def test_nested_attribute_source_chain(self):
        context = self._untyped_context()
        # 根符号即缺失：未知沿 person → dob → year 整条访问链累积来源
        result = Rule('person.dob.year >= 2000', context=context).evaluate_ternary({})
        self.assertIsNone(result.match)
        self.assertEqual(result.unknowns[0].source, ('person', 'dob', 'year'))

    # —— 线程安全 ——
    def test_thread_safety_with_policy(self):
        context = self._context(age=types.DataType.FLOAT)
        rule = Rule('age >= 18 and age < 65', context=context)
        errors_seen = []
        def worker(value):
            try:
                for _ in range(100):
                    result = rule.evaluate_ternary(value)
                    if value:
                        assert result.match in (True, False)
                    else:
                        assert result.match is None
            except Exception as error:  # pragma: no cover
                errors_seen.append(error)
        threads = [threading.Thread(target=worker, args=({'age': 30} if i % 2 else {},)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors_seen, [])

if __name__ == '__main__':
    unittest.main()
