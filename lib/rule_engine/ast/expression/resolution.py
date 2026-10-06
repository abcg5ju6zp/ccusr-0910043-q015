#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  rule_engine/ast/expression/resolution.py
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

from typing import TYPE_CHECKING, Any, Iterable

from ... import errors
from ...types import DataType
from ...types import _CollectionDataTypeDef, _DataTypeDef, _FunctionDataTypeDef, _MappingDataTypeDef
from ...unknown import UnknownReason, UnknownValue

from ..base import ExpressionBase, LiteralExpressionBase, _adjudicate, _is_reduced, _is_unknown, _settle_unknown

if TYPE_CHECKING:
    from ...engine.context import Context

class SymbolExpression(ExpressionBase):
    """项目内部接口说明。"""
    __slots__ = ('name', 'result_type', 'scope')
    def __init__(self, context: 'Context', name: str, scope: str | None = None) -> None:
        """项目内部接口说明。"""
        context.symbols.add(name)
        self.context = context
        self.name = name
        type_hint = context.resolve_type(name, scope=scope)
        if type_hint is not None:
            self.result_type = type_hint
        self.scope = scope

    def __repr__(self) -> str:
        return "<{0} name={1!r} >".format(self.__class__.__name__, self.name)

    def evaluate(self, thing: Any) -> Any:
        policy = self.context.unknown_policy
        try:
            value = self.context.resolve(thing, self.name, scope=self.scope)
        except errors.SymbolResolutionError:
            if policy is not None:
                adjudicated = _adjudicate(
                        self.context,
                        UnknownValue(UnknownReason.MISSING, source=(self.name,))
                )
                if _is_unknown(adjudicated):
                    return adjudicated
                value = adjudicated
            else:
                default_value = self.context.default_value
                if default_value is errors.UNDEFINED:
                    raise
                value = default_value
        except errors.UnknownFieldError as error:
            if policy is None:
                raise
            unknown = UnknownValue.from_error(error)
            if not unknown.source:
                unknown = unknown.derive(self.name)
            adjudicated = _adjudicate(self.context, unknown)
            if _is_unknown(adjudicated):
                return adjudicated
            value = adjudicated
        if _is_unknown(value):
            # resolver 直接返回了未知值：在缺少来源时补上当前符号名后裁决
            # （上下文没有策略时 _settle_unknown 会显式报错，未知值不会泄漏到二值世界）
            if not value.source:
                value = value.derive(self.name)
            settled = _settle_unknown(self, value)
            if _is_unknown(settled):
                return settled
            value = settled
        value = self._new_value(value, verify_type=False)

        # if the expected result type is undefined, return the value
        if self.result_type == DataType.UNDEFINED:
            return value

        try:
            return self._evaluate_typed(value)
        except (errors.SymbolTypeError, TypeError):
            # 字段存在但值无法按声明类型解释（类型不兼容或根本无法映射到数据类型）——
            # 这是“解析失败”而非“规则不匹配”
            if policy is None:
                raise
            adjudicated = _adjudicate(
                    self.context,
                    UnknownValue(
                            UnknownReason.PARSE_ERROR,
                            source=(self.name,),
                            detail='resolved value is not compatible with the declared type'
                    )
            )
            if _is_unknown(adjudicated):
                return adjudicated
            # 兜底值同样要经过类型强转与校验，保证下游运算类型一致
            try:
                return self._evaluate_typed(self._new_value(adjudicated, verify_type=False))
            except (errors.SymbolTypeError, TypeError):
                raise errors.EvaluationError(
                        "unknown policy fallback for symbol {0!r} is not compatible with its declared type".format(self.name)
                ) from None

    def _evaluate_typed(self, value: Any) -> Any:
        """对已经解析到的值执行声明类型校验。"""
        # NULLABLE(T) is T-or-None at runtime; None is always valid, and any other value is checked against the
        # unwrapped inner type
        effective_type: _DataTypeDef = self.result_type
        if DataType.is_type(effective_type, DataType.NULLABLE):
            if value is None:
                return value
            effective_type = effective_type.inner_type

        # OBJECT values are opaque to DataType.from_value; trust the schema annotation and delegate attribute-level
        # type checking to GetAttributeExpression
        if DataType.is_type(effective_type, DataType.OBJECT):
            return value

        # use DataType.from_value to raise a TypeError if value is not of a
        # compatible data type
        value_type = DataType.from_value(value)

        # if the type is the expected result type, return the value
        if DataType.is_compatible(value_type, effective_type):
            if effective_type.is_scalar:
                return value
            assert isinstance(effective_type, (_CollectionDataTypeDef, _MappingDataTypeDef))
            assert isinstance(value_type, (_CollectionDataTypeDef, _MappingDataTypeDef))
            if effective_type.value_type == DataType.UNDEFINED:
                return value
            if value_type.value_type == DataType.UNDEFINED:
                return value
            if effective_type.value_type != DataType.NULL and not effective_type.value_type_nullable and any(v is None for v in value):
                raise errors.SymbolTypeError(self.name, is_value=value, is_type=value_type, expected_type=self.result_type)
            if DataType.is_compatible(effective_type.value_type, value_type.value_type):
                return value

        # if the type is null, return the value (treat null as a special case)
        if value_type == DataType.NULL:
            return value

        raise errors.SymbolTypeError(self.name, is_value=value, is_type=value_type, expected_type=self.result_type)

    def to_graphviz(self, digraph: Any, *args: Any, **kwargs: Any) -> None:
        digraph.node(str(id(self)), "{}\nname={!r}".format(self.__class__.__name__, self.name))

class FunctionCallExpression(ExpressionBase):
    __slots__ = ('function', 'arguments',)
    arguments: tuple[ExpressionBase, ...]
    def __init__(self, context: 'Context', function: ExpressionBase, arguments: Iterable[ExpressionBase]) -> None:
        self.context = context
        self.function = function
        argument_tuple: tuple[ExpressionBase, ...] = tuple(arguments)
        if self.function.result_type != DataType.UNDEFINED:
            function_type = self.function.result_type
            self._validate_function(function_type, argument_tuple)
            assert isinstance(function_type, _FunctionDataTypeDef)
            self.result_type = function_type.return_type
        self.arguments = argument_tuple

    @classmethod
    def build(cls, context: 'Context', function: ExpressionBase, arguments: Iterable[ExpressionBase]) -> ExpressionBase:  # type: ignore[override]
        function_built = function.build()
        assert isinstance(function_built, ExpressionBase)
        built_args: list[ExpressionBase] = []
        for argument in arguments:
            argument_built = argument.build()
            assert isinstance(argument_built, ExpressionBase)
            built_args.append(argument_built)
        reduced = cls(context, function_built, tuple(built_args)).reduce()
        assert isinstance(reduced, ExpressionBase)
        return reduced

    def evaluate(self, thing: Any) -> Any:
        function = self.function.evaluate(thing)
        if _is_unknown(function):
            return function
        if not callable(function):
            raise errors.EvaluationError('data type mismatch (not a callable value)')
        arguments = tuple(argument.evaluate(thing) for argument in self.arguments)
        if any(_is_unknown(argument) for argument in arguments):
            # 任一实参未知：自定义函数不被调用，未知值携带首个未知实参的来源继续传播
            return next(argument for argument in arguments if _is_unknown(argument))
        function_name: str | None = '<unknown>'
        if self.function.result_type != DataType.UNDEFINED:
            function_type = self.function.result_type
            assert isinstance(function_type, _FunctionDataTypeDef)
            function_name = function_type.value_name
            self._validate_function(function_type, arguments)
        elif hasattr(function, '__name__'):
            function_name = function.__name__ + '?'
        try:
            result = function(*arguments)
        except errors.UnknownFieldError as error:
            if self.context.unknown_policy is None:
                raise
            result = UnknownValue.from_error(error)
        except errors.FunctionCallError as error:
            error.function_name = function_name
            raise error
        except Exception as error:
            raise errors.FunctionCallError('function call failed', error=error, function_name=function_name) from None
        if _is_unknown(result):
            result = _settle_unknown(self, result)
            if _is_unknown(result):
                return result
            # 兜底值落到下方常规路径完成返回类型校验
        result = self._new_value(result)
        if not DataType.is_compatible(DataType.from_value(result), self.result_type):
            raise errors.FunctionCallError('function call failed (data type mismatch on returned value)', function_name=function_name)
        return result

    def reduce(self) -> ExpressionBase:
        if not _is_reduced(self.function, *self.arguments):
            return self
        reduced = self.evaluate(None)
        if _is_unknown(reduced):
            # UnknownValue 无法表示为字面量表达式；保留调用节点，让每次求值重新传播
            return self
        return LiteralExpressionBase.from_value(self.context, reduced)

    def _validate_function(self, function_type: _DataTypeDef, arguments: 'tuple[Any, ...]') -> None:
        if not isinstance(function_type, _FunctionDataTypeDef):
            raise errors.EvaluationError('data type mismatch (not a callable value)')
        if function_type.minimum_arguments is not DataType.UNDEFINED:
            assert isinstance(function_type.minimum_arguments, int)
            if len(arguments) < function_type.minimum_arguments:
                raise errors.FunctionCallError(
                        "expected at least {} positional arguments".format(function_type.minimum_arguments),
                        function_name=function_type.value_name
                )
        if function_type.argument_types is not DataType.UNDEFINED:
            assert isinstance(function_type.argument_types, tuple)
            if len(arguments) > len(function_type.argument_types):
                raise errors.FunctionCallError(
                        "expected at most {} positional arguments".format(len(function_type.argument_types)),
                        function_name=function_type.value_name
                )
            for pos, (arg1, arg2_type) in enumerate(zip(arguments, function_type.argument_types), 1):
                if isinstance(arg1, ExpressionBase):
                    arg1_type = arg1.result_type
                else:
                    arg1_type = DataType.from_value(arg1)
                if not DataType.is_compatible(arg1_type, arg2_type):
                    raise errors.FunctionCallError(
                            "data type mismatch (argument #{})".format(pos),
                            function_name=function_type.value_name
                    )
                if DataType.is_type(arg1_type, DataType.NULLABLE) and not DataType.is_type(arg2_type, DataType.NULLABLE) and arg2_type != DataType.UNDEFINED:
                    raise errors.FunctionCallError(
                            "data type mismatch (argument #{} is nullable; discharge with '??' or use '&.' / '&[' for safe navigation)".format(pos),
                            function_name=function_type.value_name
                    )

    def to_graphviz(self, digraph: Any, *args: Any, **kwargs: Any) -> None:
        super(FunctionCallExpression, self).to_graphviz(digraph, *args, **kwargs)
        self.function.to_graphviz(digraph, *args, **kwargs)
        digraph.edge(str(id(self)), str(id(self.function)), label='function')
        for idx, argument in enumerate(self.arguments, 1):
            argument.to_graphviz(digraph, *args, **kwargs)
            digraph.edge(str(id(self)), str(id(argument)), label="argument #{}".format(idx))
