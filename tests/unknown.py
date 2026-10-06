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

"""未知值（三值逻辑）语义的回归测试。"""

import dataclasses
import pickle
import unittest

import rule_engine.engine as engine
import rule_engine.errors as errors
import rule_engine.types as types
from rule_engine.unknown import MASKED, UnknownPolicy, UnknownSource, UnknownValue, is_unknown

__all__ = (
    'UnknownPolicyTests',
    'UnknownValueTests',
    'UnknownDefaultCompatTests',
    'UnknownMissingTests',
    'UnknownParseErrorTests',
    'UnknownMaskedTests',
    'UnknownTruthTableTests',
    'UnknownComprehensionTests',
    'UnknownFunctionCallTests',
    'UnknownProvenanceTests',
    'UnknownSerializationTests',
)

def _resolver_with(parse_fail=(), masked=()):
    """构造一个 resolver：对 parse_fail 中的名字抛 DataParseError，对 masked 中的名字返回 MASKED。"""
    def resolver(thing, name):
        if name in masked:
            return MASKED
        if name in parse_fail:
            raise errors.DataParseError(name)
        return engine.resolve_item(thing, name)
    return resolver

class UnknownPolicyTests(unittest.TestCase):
    def test_policy_defaults(self):
        policy = UnknownPolicy()
        self.assertIsNone(policy.missing)
        self.assertIsNone(policy.parse_error)
        self.assertIsNone(policy.masked)

    def test_policy_from_value_none(self):
        self.assertIsInstance(UnknownPolicy.from_value(None), UnknownPolicy)

    def test_policy_from_value_string(self):
        policy = UnknownPolicy.from_value('propagate')
        self.assertEqual(policy.missing, 'propagate')
        self.assertEqual(policy.parse_error, 'propagate')
        self.assertEqual(policy.masked, 'propagate')

    def test_policy_from_value_mapping(self):
        policy = UnknownPolicy.from_value({'missing': 'propagate', 'masked': 'fallback'})
        self.assertEqual(policy.missing, 'propagate')
        self.assertIsNone(policy.parse_error)
        self.assertEqual(policy.masked, 'fallback')

    def test_policy_from_value_passthrough(self):
        policy = UnknownPolicy(missing='abort')
        self.assertIs(UnknownPolicy.from_value(policy), policy)

    def test_policy_invalid_action(self):
        with self.assertRaises(ValueError):
            UnknownPolicy(missing='explode')
        with self.assertRaises(ValueError):
            UnknownPolicy.from_value('explode')

    def test_policy_invalid_source(self):
        with self.assertRaises(ValueError):
            UnknownPolicy.from_value({'unknown_source': 'abort'})

    def test_policy_invalid_type(self):
        with self.assertRaises(TypeError):
            UnknownPolicy.from_value(42)

    def test_policy_action_for(self):
        policy = UnknownPolicy(missing='propagate', parse_error='fallback')
        self.assertEqual(policy.action_for(UnknownSource.MISSING), 'propagate')
        self.assertEqual(policy.action_for(UnknownSource.PARSE_ERROR), 'fallback')
        self.assertIsNone(policy.action_for(UnknownSource.MASKED))

    def test_context_policy_normalized(self):
        context = engine.Context(unknown_policy={'missing': 'propagate'})
        self.assertIsInstance(context.unknown_policy, UnknownPolicy)
        self.assertEqual(context.unknown_policy.missing, 'propagate')

class UnknownValueTests(unittest.TestCase):
    def test_is_unknown(self):
        self.assertTrue(is_unknown(UnknownValue(UnknownSource.MISSING)))
        self.assertFalse(is_unknown(None))
        self.assertFalse(is_unknown(False))
        self.assertFalse(is_unknown(0))

    def test_unknown_is_falsy(self):
        # 条件位置：UNKNOWN 视为非真
        self.assertFalse(bool(UnknownValue(UnknownSource.MISSING)))

    def test_unknown_equality_and_hash(self):
        left = UnknownValue(UnknownSource.MISSING, 'age')
        right = UnknownValue(UnknownSource.MISSING, 'age')
        other = UnknownValue(UnknownSource.MASKED, 'age')
        self.assertEqual(left, right)
        self.assertEqual(hash(left), hash(right))
        self.assertNotEqual(left, other)
        self.assertNotEqual(left, 'age')

    def test_unknown_requires_source(self):
        with self.assertRaises(TypeError):
            UnknownValue('missing')

    def test_unknown_repr_has_no_content(self):
        value = UnknownValue(UnknownSource.PARSE_ERROR, 'age')
        self.assertIn('age', repr(value))
        self.assertIn('PARSE_ERROR', repr(value))

class UnknownDefaultCompatTests(unittest.TestCase):
    """未配置 unknown_policy 时，旧规则维持二值行为。"""

    def test_missing_symbol_raises_by_default(self):
        rule = engine.Rule('missing_field == 1')
        with self.assertRaises(errors.SymbolResolutionError):
            rule.evaluate({})

    def test_missing_attribute_raises_by_default(self):
        rule = engine.Rule('obj.missing_attr == 1')
        with self.assertRaises(errors.AttributeResolutionError):
            rule.evaluate({'obj': object()})

    def test_missing_item_raises_by_default(self):
        rule = engine.Rule('data["missing_key"] == 1')
        with self.assertRaises(errors.LookupError):
            rule.evaluate({'data': {}})

    def test_default_value_still_applies_to_symbols(self):
        context = engine.Context(default_value=None)
        rule = engine.Rule('missing_field == null', context=context)
        self.assertTrue(rule.evaluate({}))

    def test_default_value_still_applies_to_attributes(self):
        context = engine.Context(default_value=None)
        rule = engine.Rule('obj.missing_attr == null', context=context)
        self.assertTrue(rule.evaluate({'obj': object()}))

    def test_default_value_does_not_apply_to_items(self):
        # 历史行为：getitem 缺失不套用 default_value
        context = engine.Context(default_value=None)
        rule = engine.Rule('data["missing_key"] == null', context=context)
        with self.assertRaises(errors.LookupError):
            rule.evaluate({'data': {}})

    def test_null_is_not_unknown(self):
        rule = engine.Rule('value == null')
        self.assertTrue(rule.evaluate({'value': None}))
        self.assertFalse(is_unknown(rule.evaluate({'value': None})))

    def test_matches_still_boolean(self):
        rule = engine.Rule('value > 1')
        self.assertIs(rule.matches({'value': 2}), True)
        self.assertIs(rule.matches({'value': 0}), False)

class UnknownMissingTests(unittest.TestCase):
    def test_propagate_symbol(self):
        context = engine.Context(unknown_policy={'missing': 'propagate'})
        rule = engine.Rule('age', context=context)
        result = rule.evaluate({})
        self.assertEqual(result, UnknownValue(UnknownSource.MISSING, 'age'))

    def test_propagate_attribute(self):
        context = engine.Context(unknown_policy={'missing': 'propagate'})
        rule = engine.Rule('obj.age', context=context)
        result = rule.evaluate({'obj': object()})
        self.assertEqual(result, UnknownValue(UnknownSource.MISSING, 'age'))

    def test_propagate_item(self):
        context = engine.Context(unknown_policy={'missing': 'propagate'})
        rule = engine.Rule('data["age"]', context=context)
        result = rule.evaluate({'data': {}})
        self.assertEqual(result, UnknownValue(UnknownSource.MISSING, 'age'))

    def test_fallback_symbol(self):
        context = engine.Context(unknown_policy={'missing': 'fallback'}, default_value=0)
        rule = engine.Rule('age', context=context)
        self.assertEqual(rule.evaluate({}), 0)

    def test_fallback_defaults_to_null(self):
        context = engine.Context(unknown_policy={'missing': 'fallback'})
        rule = engine.Rule('age', context=context)
        self.assertIsNone(rule.evaluate({}))

    def test_abort_is_default(self):
        context = engine.Context(unknown_policy={'masked': 'propagate'})
        rule = engine.Rule('age', context=context)
        with self.assertRaises(errors.SymbolResolutionError):
            rule.evaluate({})

    def test_explicit_propagate_overrides_default_value(self):
        # 显式策略优先于 default_value 的历史默认
        context = engine.Context(unknown_policy={'missing': 'propagate'}, default_value=0)
        rule = engine.Rule('age', context=context)
        self.assertEqual(rule.evaluate({}), UnknownValue(UnknownSource.MISSING, 'age'))

    def test_safe_navigation_still_returns_null(self):
        context = engine.Context(unknown_policy={'missing': 'propagate'})
        rule = engine.Rule('data&["missing_key"]', context=context)
        self.assertIsNone(rule.evaluate({'data': {}}))

class UnknownParseErrorTests(unittest.TestCase):
    def test_propagate(self):
        context = engine.Context(resolver=_resolver_with(parse_fail=('age',)), unknown_policy={'parse_error': 'propagate'})
        rule = engine.Rule('age', context=context)
        result = rule.evaluate({'age': 'not-a-number'})
        self.assertEqual(result, UnknownValue(UnknownSource.PARSE_ERROR, 'age'))

    def test_fallback(self):
        context = engine.Context(resolver=_resolver_with(parse_fail=('age',)), unknown_policy={'parse_error': 'fallback'}, default_value=0)
        rule = engine.Rule('age', context=context)
        self.assertEqual(rule.evaluate({'age': 'not-a-number'}), 0)

    def test_abort_reraises(self):
        context = engine.Context(resolver=_resolver_with(parse_fail=('age',)))
        rule = engine.Rule('age', context=context)
        with self.assertRaises(errors.DataParseError):
            rule.evaluate({'age': 'not-a-number'})

    def test_propagate_via_attribute(self):
        class Obj(object):
            @property
            def age(self):
                raise errors.DataParseError('age')
        context = engine.Context(resolver=engine.resolve_attribute, unknown_policy={'parse_error': 'propagate'})
        rule = engine.Rule('age', context=context)
        result = rule.evaluate(Obj())
        self.assertEqual(result, UnknownValue(UnknownSource.PARSE_ERROR, 'age'))

class UnknownMaskedTests(unittest.TestCase):
    def test_propagate(self):
        context = engine.Context(resolver=_resolver_with(masked=('ssn',)), unknown_policy={'masked': 'propagate'})
        rule = engine.Rule('ssn', context=context)
        result = rule.evaluate({'ssn': 'should-not-see'})
        self.assertEqual(result, UnknownValue(UnknownSource.MASKED, 'ssn'))

    def test_fallback(self):
        context = engine.Context(resolver=_resolver_with(masked=('ssn',)), unknown_policy={'masked': 'fallback'}, default_value='***')
        rule = engine.Rule('ssn', context=context)
        self.assertEqual(rule.evaluate({'ssn': 'should-not-see'}), '***')

    def test_abort_raises_masked_error(self):
        context = engine.Context(resolver=_resolver_with(masked=('ssn',)))
        rule = engine.Rule('ssn', context=context)
        with self.assertRaises(errors.SymbolMaskedError):
            rule.evaluate({'ssn': 'should-not-see'})

    def test_masked_attribute(self):
        @dataclasses.dataclass
        class Obj:
            ssn: str
        obj_type = types.DataType.OBJECT.from_dataclass('Obj', Obj)
        context = engine.Context(type_resolver={'obj': obj_type}, unknown_policy={'masked': 'propagate'})
        rule = engine.Rule('obj.ssn', context=context)
        result = rule.evaluate({'obj': Obj(MASKED)})  # type: ignore[arg-type]
        self.assertEqual(result, UnknownValue(UnknownSource.MASKED, 'ssn'))

    def test_masked_item(self):
        context = engine.Context(unknown_policy={'masked': 'propagate'})
        rule = engine.Rule('data["ssn"]', context=context)
        result = rule.evaluate({'data': {'ssn': MASKED}})
        self.assertEqual(result, UnknownValue(UnknownSource.MASKED, 'ssn'))

class UnknownTruthTableTests(unittest.TestCase):
    """所有运算符遵循同一真值表：Kleene 三值逻辑 + 值位置严格传播。"""

    def setUp(self):
        self.context = engine.Context(unknown_policy='propagate')

    def _eval(self, text, thing=None):
        return engine.Rule(text, context=self.context).evaluate(thing or {})

    # -- 布尔短路（Kleene） --
    def test_and_truth_table(self):
        self.assertIs(self._eval('false and missing'), False)
        self.assertIs(self._eval('true and true'), True)
        self.assertIs(self._eval('true and false'), False)
        self.assertEqual(self._eval('true and missing'), UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertEqual(self._eval('missing and true'), UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertIs(self._eval('missing and false'), False)
        self.assertEqual(self._eval('missing and other_missing'), UnknownValue(UnknownSource.MISSING, 'missing'))

    def test_or_truth_table(self):
        self.assertIs(self._eval('true or missing'), True)
        self.assertIs(self._eval('false or true'), True)
        self.assertIs(self._eval('false or false'), False)
        self.assertEqual(self._eval('false or missing'), UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertEqual(self._eval('missing or false'), UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertIs(self._eval('missing or true'), True)
        self.assertEqual(self._eval('missing or other_missing'), UnknownValue(UnknownSource.MISSING, 'missing'))

    def test_not_truth_table(self):
        self.assertIs(self._eval('not true'), False)
        self.assertIs(self._eval('not false'), True)
        self.assertEqual(self._eval('not missing'), UnknownValue(UnknownSource.MISSING, 'missing'))

    def test_and_short_circuits_right_side(self):
        # false and ... 不求值右侧（否则运行时触发除零错误）
        self.assertIs(self._eval('false and 1 / zero == 0', {'zero': 0}), False)

    def test_or_short_circuits_right_side(self):
        self.assertIs(self._eval('true or 1 / zero == 0', {'zero': 0}), True)

    # -- 比较（严格传播） --
    def test_equality_propagates(self):
        self.assertEqual(self._eval('missing == 1'), UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertEqual(self._eval('1 == missing'), UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertEqual(self._eval('missing != 1'), UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertEqual(self._eval('missing == other_missing'), UnknownValue(UnknownSource.MISSING, 'missing'))

    def test_ordering_propagates(self):
        for op in ('<', '<=', '>', '>='):
            self.assertEqual(self._eval('missing {} 1'.format(op)), UnknownValue(UnknownSource.MISSING, 'missing'))
            self.assertEqual(self._eval('1 {} missing'.format(op)), UnknownValue(UnknownSource.MISSING, 'missing'))

    def test_fuzzy_propagates(self):
        self.assertEqual(self._eval('missing =~ "a"'), UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertEqual(self._eval('"abc" =~ missing'), UnknownValue(UnknownSource.MISSING, 'missing'))

    def test_contains_propagates(self):
        self.assertEqual(self._eval('1 in missing'), UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertEqual(self._eval('missing in [1, 2]'), UnknownValue(UnknownSource.MISSING, 'missing'))

    # -- 算术 / 位运算（严格传播） --
    def test_arithmetic_propagates(self):
        for text in ('missing + 1', '1 + missing', 'missing - 1', 'missing * 2', 'missing / 2', 'missing % 2', 'missing ** 2'):
            self.assertEqual(self._eval(text), UnknownValue(UnknownSource.MISSING, 'missing'), text)

    def test_bitwise_propagates(self):
        for text in ('missing & 1', 'missing | 1', 'missing ^ 1', 'missing << 1', 'missing >> 1'):
            self.assertEqual(self._eval(text), UnknownValue(UnknownSource.MISSING, 'missing'), text)

    def test_unary_minus_propagates(self):
        self.assertEqual(self._eval('-missing'), UnknownValue(UnknownSource.MISSING, 'missing'))

    # -- 默认值运算（?? 吸收 UNKNOWN） --
    def test_coalesce_absorbs_unknown(self):
        self.assertEqual(self._eval('missing ?? 42'), 42)
        self.assertEqual(self._eval('1 ?? missing'), 1)
        # 左侧未知时取右操作数；右侧也未知则传播右侧的来源
        self.assertEqual(self._eval('missing ?? other_missing'), UnknownValue(UnknownSource.MISSING, 'other_missing'))

    def test_coalesce_still_handles_null(self):
        self.assertEqual(self._eval('null ?? 42'), 42)

    # -- 三元表达式（条件位置：UNKNOWN 视为非真） --
    def test_ternary_unknown_condition(self):
        self.assertEqual(self._eval('missing ? 1 : 2'), 2)
        self.assertEqual(self._eval('true ? 1 : missing'), 1)
        self.assertEqual(self._eval('false ? 1 : missing'), UnknownValue(UnknownSource.MISSING, 'missing'))

    # -- 容器字面量（严格传播） --
    def test_array_literal_propagates(self):
        self.assertEqual(self._eval('[missing, 1]'), UnknownValue(UnknownSource.MISSING, 'missing'))

    def test_set_literal_propagates(self):
        self.assertEqual(self._eval('{missing, 1}'), UnknownValue(UnknownSource.MISSING, 'missing'))

    def test_mapping_literal_propagates(self):
        self.assertEqual(self._eval('{"k": missing}'), UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertEqual(self._eval('{missing: 1}'), UnknownValue(UnknownSource.MISSING, 'missing'))

    # -- 访问运算（严格传播） --
    def test_getitem_on_unknown(self):
        self.assertEqual(self._eval('missing[0]'), UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertEqual(self._eval('[1, 2][missing]'), UnknownValue(UnknownSource.MISSING, 'missing'))

    def test_getattr_on_unknown(self):
        self.assertEqual(self._eval('missing.attr'), UnknownValue(UnknownSource.MISSING, 'missing'))

    def test_getslice_on_unknown(self):
        self.assertEqual(self._eval('missing[0:2]'), UnknownValue(UnknownSource.MISSING, 'missing'))

    # -- 顶层求值 / 过滤 --
    def test_matches_collapses_unknown_to_false(self):
        rule = engine.Rule('missing > 1', context=self.context)
        self.assertIs(rule.matches({}), False)

    def test_evaluate_returns_unknown(self):
        rule = engine.Rule('missing > 1', context=self.context)
        self.assertEqual(rule.evaluate({}), UnknownValue(UnknownSource.MISSING, 'missing'))

    def test_filter_excludes_unknown_rows(self):
        rule = engine.Rule('score > 10', context=self.context)
        things = [{'score': 20}, {}, {'score': 5}]
        self.assertEqual(list(rule.filter(things)), [{'score': 20}])

class UnknownComprehensionTests(unittest.TestCase):
    def setUp(self):
        self.context = engine.Context(unknown_policy='propagate')

    def test_unknown_iterable(self):
        rule = engine.Rule('[x for x in items]', context=self.context)
        self.assertEqual(rule.evaluate({}), UnknownValue(UnknownSource.MISSING, 'items'))

    def test_unknown_condition_drops_all_elements(self):
        rule = engine.Rule('[x for x in items if x > threshold]', context=self.context)
        # threshold 缺失 → 每个元素的条件都是 UNKNOWN → 全部被过滤
        self.assertEqual(rule.evaluate({'items': (0, 2, 3)}), ())
        # threshold 到位后正常过滤
        self.assertEqual(rule.evaluate({'items': (0, 2, 3), 'threshold': 1}), (2, 3))

    def test_unknown_element_condition_drops_element(self):
        rule = engine.Rule('[x for x in items if x > 1]', context=self.context)
        unknown = UnknownValue(UnknownSource.MISSING, 'ghost')
        self.assertEqual(rule.evaluate({'items': (unknown, 2, 0)}), (2,))

    def test_unknown_result_propagates(self):
        rule = engine.Rule('[x + missing for x in items]', context=self.context)
        result = rule.evaluate({'items': (1, 2)})
        self.assertEqual(result, UnknownValue(UnknownSource.MISSING, 'missing'))

class UnknownFunctionCallTests(unittest.TestCase):
    def setUp(self):
        self.context = engine.Context(unknown_policy='propagate')

    def test_unknown_argument_short_circuits(self):
        calls = []
        def tracker(x):
            calls.append(x)
            return x
        context = engine.Context(
                resolver=lambda thing, name: tracker if name == 'fn' else engine.resolve_item(thing, name),
                unknown_policy='propagate'
        )
        rule = engine.Rule('fn(missing)', context=context)
        result = rule.evaluate({})
        self.assertEqual(result, UnknownValue(UnknownSource.MISSING, 'missing'))
        self.assertEqual(calls, [])

    def test_unknown_function_propagates(self):
        rule = engine.Rule('missing_fn(1)', context=self.context)
        self.assertEqual(rule.evaluate({}), UnknownValue(UnknownSource.MISSING, 'missing_fn'))

    def test_function_returning_unknown(self):
        def make_unknown():
            return UnknownValue(UnknownSource.PARSE_ERROR, 'computed')
        context = engine.Context(
                resolver=lambda thing, name: make_unknown if name == 'fn' else engine.resolve_item(thing, name),
                unknown_policy='propagate'
        )
        rule = engine.Rule('fn()', context=context)
        self.assertEqual(rule.evaluate({}), UnknownValue(UnknownSource.PARSE_ERROR, 'computed'))

    def test_builtin_with_unknown_argument(self):
        rule = engine.Rule('$abs(missing)', context=self.context)
        self.assertEqual(rule.evaluate({}), UnknownValue(UnknownSource.MISSING, 'missing'))

class UnknownProvenanceTests(unittest.TestCase):
    """未知来源被保留，且不暴露字段内容。"""

    def test_provenance_survives_propagation(self):
        context = engine.Context(unknown_policy='propagate')
        rule = engine.Rule('secret_field + 1', context=context)
        result = rule.evaluate({})
        self.assertIsInstance(result, UnknownValue)
        self.assertEqual(result.source, UnknownSource.MISSING)
        self.assertEqual(result.symbol, 'secret_field')

    def test_provenance_does_not_leak_value(self):
        secret = 's3cr3t-value'
        context = engine.Context(resolver=_resolver_with(masked=('ssn',)), unknown_policy='propagate')
        rule = engine.Rule('ssn', context=context)
        result = rule.evaluate({'ssn': secret})
        self.assertNotIn(secret, repr(result))
        self.assertFalse(hasattr(result, 'value'))
        self.assertFalse(hasattr(result, 'thing'))

    def test_first_unknown_wins(self):
        context = engine.Context(unknown_policy='propagate')
        rule = engine.Rule('first_missing and second_missing', context=context)
        result = rule.evaluate({})
        self.assertEqual(result.symbol, 'first_missing')

    def test_unknown_value_is_picklable(self):
        value = UnknownValue(UnknownSource.MASKED, 'ssn')
        self.assertEqual(pickle.loads(pickle.dumps(value)), value)

class UnknownSerializationTests(unittest.TestCase):
    def test_context_pickle_roundtrip(self):
        context = engine.Context(unknown_policy={'missing': 'propagate', 'masked': 'fallback'}, default_value=0)
        context2 = pickle.loads(pickle.dumps(context))
        self.assertEqual(context2.unknown_policy.missing, 'propagate')
        self.assertEqual(context2.unknown_policy.masked, 'fallback')
        self.assertIsNone(context2.unknown_policy.parse_error)
        rule = engine.Rule('age', context=context2)
        self.assertEqual(rule.evaluate({}), UnknownValue(UnknownSource.MISSING, 'age'))

    def test_context_pickle_default_policy(self):
        context = engine.Context()
        context2 = pickle.loads(pickle.dumps(context))
        self.assertIsInstance(context2.unknown_policy, UnknownPolicy)
        rule = engine.Rule('missing_field', context=context2)
        with self.assertRaises(errors.SymbolResolutionError):
            rule.evaluate({})

    def test_rule_pickle_with_policy(self):
        context = engine.Context(unknown_policy='propagate')
        rule = engine.Rule('age > 18', context=context)
        rule2 = pickle.loads(pickle.dumps(rule))
        self.assertEqual(rule2.evaluate({}), UnknownValue(UnknownSource.MISSING, 'age'))
