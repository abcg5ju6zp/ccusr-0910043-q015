#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  rule_engine/ast/expression/access.py
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

import collections.abc
import operator
from typing import TYPE_CHECKING, Any

from ... import builtins as _builtins
from ... import errors
from ...suggestions import suggest_symbol
from ...types import DataType, coerce_value
from ...types import _DataTypeDef
from ...types import is_integer_number as _is_integer_number
from ...unknown import UnknownReason, UnknownValue

from ..base import (
        ExpressionBase,
        LiteralExpressionBase,
        _assert_not_nullable,
        _is_reduced,
        _is_unknown,
        _resolve_type,
        _settle_unknown,
)
from ..literal import BooleanExpression, NullExpression

if TYPE_CHECKING:
    from ...engine.context import Context

class ContainsExpression(ExpressionBase):
    """项目内部接口说明。"""
    __slots__ = ('container', 'member')
    result_type: _DataTypeDef = DataType.BOOLEAN
    def __init__(self, context: 'Context', container: ExpressionBase, member: ExpressionBase) -> None:
        _assert_not_nullable(container.result_type, role='containment container')
        container_type = container.result_type
        member_type = DataType.NULLABLE.unwrap(member.result_type)
        if container_type == DataType.BYTES or container_type == DataType.STRING:
            if member_type != DataType.UNDEFINED and member_type != container_type:
                raise errors.EvaluationError('data type mismatch')
        elif DataType.is_type(_resolve_type(container_type, context), DataType.OBJECT):
            raise errors.EvaluationError('data type mismatch (containment check on OBJECT)')
        elif container_type != DataType.UNDEFINED and container_type.is_scalar:
            raise errors.EvaluationError('data type mismatch')
        self.context = context
        self.member = member
        self.container = container

    @classmethod
    def build(cls, context: 'Context', container: ExpressionBase, member: ExpressionBase) -> ExpressionBase:  # type: ignore[override]
        container_built = container.build()
        assert isinstance(container_built, ExpressionBase)
        member_built = member.build()
        assert isinstance(member_built, ExpressionBase)
        reduced = cls(context, container_built, member_built).reduce()
        assert isinstance(reduced, ExpressionBase)
        return reduced

    def __repr__(self) -> str:
        return "<{0} container={1!r} member={2!r} >".format(self.__class__.__name__, self.container, self.member)

    def evaluate(self, thing: Any) -> Any:
        container_value = self.container.evaluate(thing)
        if _is_unknown(container_value):
            return container_value
        container_value_type = DataType.from_value(container_value)
        member_value = self.member.evaluate(thing)
        if _is_unknown(member_value):
            return member_value
        if container_value_type == DataType.BYTES or container_value_type == DataType.STRING:
            if DataType.from_value(member_value) != container_value_type:
                from ..base import _reconcile_type_error
                reconciled = _reconcile_type_error(
                        self.context, self.container, self.member,
                        detail='containment member type must match the bytes/string container'
                )
                if reconciled is not errors.UNDEFINED:
                    return reconciled
                raise errors.EvaluationError('data type mismatch')
        result = member_value in container_value
        if not result:
            # 未命中但容器含未知成员 / 未知键：待查项可能正是未知值，结论不可确定
            members: collections.abc.Iterable[Any]
            if isinstance(container_value, (set, frozenset, tuple)):
                members = container_value
            elif isinstance(container_value, collections.abc.Mapping):
                members = container_value.keys()
            else:
                members = ()
            pending = next((member for member in members if _is_unknown(member)), None)
            if pending is not None:
                return pending
        return bool(result)

    def reduce(self) -> ExpressionBase:
        if not _is_reduced(self.container, self.member):
            return self
        return BooleanExpression(self.context, self.evaluate(None))

    def to_graphviz(self, digraph: Any, *args: Any, **kwargs: Any) -> None:
        super(ContainsExpression, self).to_graphviz(digraph, *args, **kwargs)
        self.container.to_graphviz(digraph, *args, **kwargs)
        self.member.to_graphviz(digraph, *args, **kwargs)
        digraph.edge(str(id(self)), str(id(self.container)), label='container')
        digraph.edge(str(id(self)), str(id(self.member)), label='member')

class GetAttributeExpression(ExpressionBase):
    """项目内部接口说明。"""
    __slots__ = ('name', 'object', 'safe', '_object_type')
    def __init__(self, context: 'Context', object_: ExpressionBase, name: str, safe: bool = False) -> None:
        """项目内部接口说明。"""
        self.context = context
        self.object = object_
        self._object_type = None
        if not safe:
            _assert_not_nullable(self.object.result_type, role='attribute access target')
        object_type = DataType.NULLABLE.unwrap(self.object.result_type)
        if object_type != DataType.UNDEFINED:
            if not (object_type == DataType.NULL and safe):
                resolved_object_type = _resolve_type(object_type, context)
                if DataType.is_type(resolved_object_type, DataType.OBJECT):
                    if name not in resolved_object_type.attributes:
                        raise errors.ObjectAttributeError(
                                name,
                                resolved_object_type,
                                suggestion=suggest_symbol(name, resolved_object_type.attributes.keys())
                        )
                    self._object_type = resolved_object_type
                    attribute_type = _resolve_type(resolved_object_type.attributes[name], context)
                    self.result_type = attribute_type
                else:
                    try:
                        self.result_type = context.resolve_attribute_type(object_type, name)
                    except errors.AttributeResolutionError as error:
                        # this is necessary because MAPPING objects can have their keys accessed as attributes
                        if not DataType.is_type(object_type, DataType.MAPPING):
                            raise error
                        if not context.mapping_attribute_lookup:
                            raise errors.EvaluationError(
                                    "attribute access on a MAPPING is disabled - use mapping[{0!r}] instead, "
                                    "or set mapping_attribute_lookup=True on the Context for v4-compatible "
                                    "behavior (deprecated, removal scheduled for v6.0)".format(name)
                            )
                        # leave the result type undefined because the name could be a mapping key or attribute
                if DataType.is_type(self.object.result_type, DataType.NULLABLE) and self.result_type != DataType.UNDEFINED:
                    self.result_type = DataType.NULLABLE.wrap(self.result_type)
        self.name = name
        self.safe = safe

    @classmethod
    def build(cls, context: 'Context', object_: ExpressionBase, name: str, safe: bool = False) -> ExpressionBase:  # type: ignore[override]
        object_built = object_.build()
        assert isinstance(object_built, ExpressionBase)
        reduced = cls(context, object_built, name, safe=safe).reduce()
        assert isinstance(reduced, ExpressionBase)
        return reduced

    def __repr__(self) -> str:
        return "<{0} name={1!r} >".format(self.__class__.__name__, self.name)

    def evaluate(self, thing: Any) -> Any:
        policy = self.context.unknown_policy
        resolved_obj = self.object.evaluate(thing)
        if _is_unknown(resolved_obj):
            return resolved_obj.derive(self.name)
        if resolved_obj is None and self.safe:
            return resolved_obj
        if resolved_obj is None and DataType.is_type(self.object.result_type, DataType.NULLABLE):
            raise errors.EvaluationError(
                    "attribute access on a null value (use ?. to safely navigate a NULLABLE expression)"
            )

        def _missing() -> Any:
            if policy is None:
                return errors.UNDEFINED
            return _settle_unknown(self, UnknownValue(UnknownReason.MISSING, source=(self.name,)))

        if self._object_type is not None:
            try:
                value = self._object_type.accessor(resolved_obj, self.name)
            except errors.UnknownFieldError as error:
                if policy is None:
                    raise
                unknown = UnknownValue.from_error(error)
                if not unknown.source:
                    unknown = unknown.derive(self.name)
                return _settle_unknown(self, unknown)
            except (AttributeError, KeyError):
                missing = _missing()
                if missing is not errors.UNDEFINED:
                    return missing
                default_value = self.context.default_value
                if default_value is errors.UNDEFINED:
                    raise errors.ObjectAttributeError(
                            self.name,
                            self._object_type,
                            thing=thing,
                            suggestion=suggest_symbol(self.name, self._object_type.attributes.keys())
                    ) from None
                value = default_value
            if _is_unknown(value):
                return _settle_unknown(self, value)
            return self._new_value(value, verify_type=False)

        attribute_error = None
        try:
            value = self.context.resolve_attribute(thing, resolved_obj, self.name)
        except errors.UnknownFieldError as error:
            if policy is None:
                raise
            unknown = UnknownValue.from_error(error)
            if not unknown.source:
                unknown = unknown.derive(self.name)
            return _settle_unknown(self, unknown)
        except errors.AttributeTypeError:
            if policy is None:
                raise
            return _settle_unknown(
                    self,
                    UnknownValue(
                            UnknownReason.PARSE_ERROR,
                            source=(self.name,),
                            detail='attribute resolved to an incorrect datatype'
                    )
            )
        except errors.AttributeResolutionError as error:
            attribute_error = error
        else:
            if _is_unknown(value):
                return _settle_unknown(self, value)
            return self._new_value(value, verify_type=False)

        if isinstance(resolved_obj, collections.abc.Mapping) and not isinstance(resolved_obj, _builtins.Builtins):
            if not self.context.mapping_attribute_lookup:
                raise attribute_error
            self.context._warn_mapping_fallback(self.name)

        try:
            value = self.context.resolve(resolved_obj, self.name)
        except errors.UnknownFieldError as error:
            if policy is None:
                raise
            unknown = UnknownValue.from_error(error)
            if not unknown.source:
                unknown = unknown.derive(self.name)
            return _settle_unknown(self, unknown)
        except errors.SymbolResolutionError as symbol_error:
            missing = _missing()
            if missing is not errors.UNDEFINED:
                return missing
            default_value = self.context.default_value
            if default_value is errors.UNDEFINED:
                suggestion = attribute_error.suggestion or symbol_error.suggestion
                if attribute_error.suggestion and symbol_error.suggestion:
                    # if there are two suggestions, select the best one
                    suggestion = suggest_symbol(self.name, (attribute_error.suggestion, symbol_error.suggestion))
                attribute_error.suggestion = suggestion
                raise attribute_error from None
            value = default_value
        if _is_unknown(value):
            return _settle_unknown(self, value)
        return self._new_value(value, verify_type=False)

    def reduce(self) -> ExpressionBase:
        if not _is_reduced(self.object):
            return self
        evaluated = self.evaluate(None)
        if _is_unknown(evaluated):
            return self
        literal = LiteralExpressionBase.from_value(self.context, evaluated)
        if literal.result_type == DataType.FUNCTION and DataType.is_compatible(self.result_type, DataType.FUNCTION):
            literal.result_type = self.result_type
        return literal

    def to_graphviz(self, digraph: Any, *args: Any, **kwargs: Any) -> None:
        digraph.node(str(id(self)), "{}\nname={!r}".format(self.__class__.__name__, self.name))
        self.object.to_graphviz(digraph, *args, **kwargs)
        digraph.edge(str(id(self)), str(id(self.object)))

class GetItemExpression(ExpressionBase):
    """项目内部接口说明。"""
    __slots__ = ('container', 'item', 'safe')
    def __init__(self, context: 'Context', container: ExpressionBase, item: ExpressionBase, safe: bool = False) -> None:
        """项目内部接口说明。"""
        self.context = context
        self.container = container
        if not safe:
            _assert_not_nullable(container.result_type, role='item access container')
        container_type = DataType.NULLABLE.unwrap(container.result_type)
        resolved_container_type = _resolve_type(container_type, context)
        if container_type == DataType.BYTES:
            if not DataType.is_compatible(item.result_type, DataType.FLOAT):
                raise errors.EvaluationError('data type mismatch (not an integer number)')
            self.result_type = DataType.FLOAT
        elif container_type == DataType.STRING:
            if not DataType.is_compatible(item.result_type, DataType.FLOAT):
                raise errors.EvaluationError('data type mismatch (not an integer number)')
            self.result_type = DataType.STRING
        elif DataType.is_type(resolved_container_type, DataType.ARRAY):
            if not DataType.is_compatible(item.result_type, DataType.FLOAT):
                raise errors.EvaluationError('data type mismatch (not an integer number)')
            self.result_type = _resolve_type(resolved_container_type.value_type, context)
        elif DataType.is_type(resolved_container_type, DataType.MAPPING):
            if not (safe or DataType.is_compatible(item.result_type, resolved_container_type.key_type)):
                raise errors.LookupError(errors.UNDEFINED, errors.UNDEFINED)
            self.result_type = _resolve_type(resolved_container_type.value_type, context)
        elif DataType.is_type(resolved_container_type, DataType.SET):
            raise errors.EvaluationError('data type mismatch (container is a set)')
        elif DataType.is_type(resolved_container_type, DataType.OBJECT):
            raise errors.EvaluationError(
                    "data type mismatch (item access on OBJECT - use {0}.attribute instead)".format(resolved_container_type.name)
            )
        elif container_type != DataType.UNDEFINED:
            if not (container_type == DataType.NULL and safe):
                raise errors.EvaluationError('data type mismatch')
        if DataType.is_type(container.result_type, DataType.NULLABLE) and self.result_type != DataType.UNDEFINED:
            self.result_type = DataType.NULLABLE.wrap(self.result_type)
        self.item = item
        self.safe = safe

    @classmethod
    def build(cls, context: 'Context', container: ExpressionBase, item: ExpressionBase, safe: bool = False) -> ExpressionBase:  # type: ignore[override]
        container_built = container.build()
        assert isinstance(container_built, ExpressionBase)
        item_built = item.build()
        assert isinstance(item_built, ExpressionBase)
        reduced = cls(context, container_built, item_built, safe=safe).reduce()
        assert isinstance(reduced, ExpressionBase)
        return reduced

    def __repr__(self) -> str:
        return "<{0} container={1!r} item={2!r} >".format(self.__class__.__name__, self.container, self.item)

    def evaluate(self, thing: Any) -> Any:
        resolved_obj = self.container.evaluate(thing)
        if _is_unknown(resolved_obj):
            # 容器未知时键仍照常求值（保持与普通运算一致的及早求值），随后把键名补进来源链
            resolved_item = self.item.evaluate(thing)
            if _is_unknown(resolved_item):
                return resolved_item
            if isinstance(resolved_item, (str, int, float)):
                return resolved_obj.derive(str(resolved_item))
            return resolved_obj
        if resolved_obj is None:
            if self.safe:
                return resolved_obj
            raise errors.EvaluationError('data type mismatch (container is null)')

        resolved_item = self.item.evaluate(thing)
        if _is_unknown(resolved_item):
            return resolved_item
        if isinstance(resolved_obj, (bytes, str, tuple)):
            if not _is_integer_number(resolved_item):
                from ..base import _reconcile_type_error
                reconciled = _reconcile_type_error(self.context, self.item, detail='index must be an integer number')
                if reconciled is not errors.UNDEFINED:
                    return reconciled
                raise errors.EvaluationError('data type mismatch (not an integer number)')
            resolved_item = int(resolved_item)
        try:
            value = operator.getitem(resolved_obj, resolved_item)
        except (IndexError, KeyError):
            if self.context.unknown_policy is not None:
                # 键缺失同样是“未知”；安全导航与非安全导航只是在无策略时是否回落到 null 的区别，
                # 有策略时统一按策略裁决，并保留键名作为来源
                return _settle_unknown(self, UnknownValue(UnknownReason.MISSING, source=(str(resolved_item),)))
            if self.safe:
                return None
            raise errors.LookupError(resolved_obj, resolved_item)
        return self._new_value(value, verify_type=False)

    def reduce(self) -> ExpressionBase:
        if DataType.is_type(self.container.result_type, DataType.MAPPING):
            if self.safe and not DataType.is_compatible(self.item.result_type, self.container.result_type.key_type):
                return NullExpression(self.context)
        if _is_reduced(self.container, self.item):
            evaluated = self.evaluate(None)
            if _is_unknown(evaluated):
                return self
            return LiteralExpressionBase.from_value(self.context, evaluated)
        return self

    def to_graphviz(self, digraph: Any, *args: Any, **kwargs: Any) -> None:
        super(GetItemExpression, self).to_graphviz(digraph, *args, **kwargs)
        self.container.to_graphviz(digraph, *args, **kwargs)
        self.item.to_graphviz(digraph, *args, **kwargs)
        digraph.edge(str(id(self)), str(id(self.container)), label='container')
        digraph.edge(str(id(self)), str(id(self.item)), label='item')

class GetSliceExpression(ExpressionBase):
    """项目内部接口说明。"""
    __slots__ = ('container', 'start', 'stop', 'safe')
    def __init__(
            self,
            context: 'Context',
            container: ExpressionBase,
            start: ExpressionBase | None = None,
            stop: ExpressionBase | None = None, safe: bool = False
    ) -> None:
        """项目内部接口说明。"""
        self.context = context
        self.container = container
        if not safe:
            _assert_not_nullable(container.result_type, role='slice container')
        container_type = DataType.NULLABLE.unwrap(container.result_type)
        if container_type == DataType.BYTES:
            self.result_type = DataType.BYTES
        elif container_type == DataType.STRING:
            self.result_type = DataType.STRING
        # check against __class__ so the parent class is dynamic in case it changes in the future, what we're doing here
        # is explicitly checking if result_type is an array with out checking the value_type
        elif DataType.is_type(container_type, DataType.ARRAY):
            self.result_type = container_type
        elif DataType.is_type(container_type, DataType.SET):
            raise errors.EvaluationError('data type mismatch (container is a set)')
        elif container_type != DataType.UNDEFINED:
            if not (container_type == DataType.NULL and safe):
                raise errors.EvaluationError('data type mismatch')
        if DataType.is_type(container.result_type, DataType.NULLABLE) and self.result_type != DataType.UNDEFINED:
            self.result_type = DataType.NULLABLE.wrap(self.result_type)
        self.start = start or LiteralExpressionBase.from_value(context, 0)
        self.stop = stop or LiteralExpressionBase.from_value(context, None)
        self.safe = safe

    @classmethod
    def build(  # type: ignore[override]
            cls,
            context: 'Context',
            container: ExpressionBase,
            start: ExpressionBase | None = None,
            stop: ExpressionBase | None = None,
            safe: bool = False
    ) -> ExpressionBase:
        if start is not None:
            start_built = start.build()
            assert isinstance(start_built, ExpressionBase)
            start = start_built
        if stop is not None:
            stop_built = stop.build()
            assert isinstance(stop_built, ExpressionBase)
            stop = stop_built
        container_built = container.build()
        assert isinstance(container_built, ExpressionBase)
        reduced = cls(context, container_built, start=start, stop=stop, safe=safe).reduce()
        assert isinstance(reduced, ExpressionBase)
        return reduced

    def __repr__(self) -> str:
        return "<{0} container={1!r} start={2!r} stop={3!r} >".format(self.__class__.__name__, self.container, self.start, self.stop)

    def evaluate(self, thing: Any) -> Any:
        resolved_obj = self.container.evaluate(thing)
        if _is_unknown(resolved_obj):
            return resolved_obj
        if resolved_obj is None:
            if self.safe:
                return resolved_obj
            raise errors.EvaluationError('data type mismatch')

        resolved_start = self.start.evaluate(thing)
        if _is_unknown(resolved_start):
            return resolved_start
        if resolved_start is not None:
            if not _is_integer_number(resolved_start):
                from ..base import _reconcile_type_error
                reconciled = _reconcile_type_error(self.context, self.start, detail='slice start must be an integer number')
                if reconciled is not errors.UNDEFINED:
                    return reconciled
                raise errors.EvaluationError('data type mismatch (not an integer number)')
            resolved_start = int(resolved_start)
        resolved_stop = self.stop.evaluate(thing)
        if _is_unknown(resolved_stop):
            return resolved_stop
        if resolved_stop is not None:
            if not _is_integer_number(resolved_stop):
                from ..base import _reconcile_type_error
                reconciled = _reconcile_type_error(self.context, self.stop, detail='slice stop must be an integer number')
                if reconciled is not errors.UNDEFINED:
                    return reconciled
                raise errors.EvaluationError('data type mismatch (not an integer number)')
            resolved_stop = int(resolved_stop)
        value = operator.getitem(resolved_obj, slice(resolved_start, resolved_stop))
        return coerce_value(value, verify_type=False)

    def reduce(self) -> ExpressionBase:
        if not _is_reduced(self.container, self.start, self.stop):
            return self
        return LiteralExpressionBase.from_value(self.context, self.evaluate(None))

    def to_graphviz(self, digraph: Any, *args: Any, **kwargs: Any) -> None:
        super(GetSliceExpression, self).to_graphviz(digraph, *args, **kwargs)
        self.container.to_graphviz(digraph, *args, **kwargs)
        self.start.to_graphviz(digraph, *args, **kwargs)
        self.stop.to_graphviz(digraph, *args, **kwargs)
        digraph.edge(str(id(self)), str(id(self.container)), label='container')
        digraph.edge(str(id(self)), str(id(self.start)), label='start')
        digraph.edge(str(id(self)), str(id(self.stop)), label='stop')
