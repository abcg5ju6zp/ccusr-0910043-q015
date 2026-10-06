#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  rule_engine/ast/binary/arithmetic.py
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

import datetime
import functools
import operator
from typing import Any, Callable

from ... import errors
from ...types import DataType, coerce_value
from ...types import _DataTypeDef

from ..base import (
        _TYPE_GUARD_OK,
        _assert_is_bytes,
        _assert_is_natural_number,
        _assert_is_numeric,
        _assert_is_string,
        _assert_not_nullable,
        _is_reduced,
        _is_unknown,
        _reconcile_type_error,
        _type_guard,
)
from .base import BinaryExpressionBase

class AddExpression(BinaryExpressionBase):
    """项目内部接口说明。"""
    compatible_types: tuple[_DataTypeDef, ...] = (DataType.BYTES, DataType.FLOAT, DataType.STRING, DataType.DATETIME, DataType.TIMEDELTA)
    result_type: _DataTypeDef = DataType.UNDEFINED

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(AddExpression, self).__init__(*args, **kwargs)
        _assert_not_nullable(self.left.result_type, role="left operand of '+'")
        _assert_not_nullable(self.right.result_type, role="right operand of '+'")
        if self.left.result_type != DataType.UNDEFINED and self.right.result_type != DataType.UNDEFINED:
            if self.left.result_type == DataType.DATETIME:
                if self.right.result_type != DataType.TIMEDELTA:
                    raise errors.EvaluationError('data type mismatch')
                self.result_type = self.left.result_type
            elif self.left.result_type == DataType.TIMEDELTA:
                if self.right.result_type not in (DataType.DATETIME, DataType.TIMEDELTA):
                    raise errors.EvaluationError('data type mismatch')
                self.result_type = self.right.result_type
            elif self.left.result_type != self.right.result_type:
                raise errors.EvaluationError('data type mismatch')
            else:
                self.result_type = self.left.result_type

    def _op_add(self, thing: Any) -> Any:
        left_value = self.left.evaluate(thing)
        if _is_unknown(left_value):
            return left_value
        right_value = self.right.evaluate(thing)
        if _is_unknown(right_value):
            return right_value
        if isinstance(left_value, datetime.datetime):
            if not isinstance(right_value, datetime.timedelta):
                reconciled = _reconcile_type_error(
                        self.context, self.left, self.right,
                        detail="right operand of '+' must be a timedelta"
                )
                if reconciled is not errors.UNDEFINED:
                    return reconciled
                raise errors.EvaluationError('data type mismatch (not a timedelta value)')
        elif isinstance(left_value, datetime.timedelta):
            if not isinstance(right_value, (datetime.timedelta, datetime.datetime)):
                reconciled = _reconcile_type_error(
                        self.context, self.left, self.right,
                        detail="right operand of '+' must be a datetime or timedelta"
                )
                if reconciled is not errors.UNDEFINED:
                    return reconciled
                raise errors.EvaluationError('data type mismatch (not a datetime or timedelta value)')
        elif isinstance(left_value, bytes) or isinstance(right_value, bytes):
            guarded = _type_guard(self.context, (self.left, self.right), "'+' operands must be bytes", _assert_is_bytes, left_value, right_value)
            if guarded is not _TYPE_GUARD_OK:
                return guarded
        elif isinstance(left_value, str) or isinstance(right_value, str):
            guarded = _type_guard(self.context, (self.left, self.right), "'+' operands must be strings", _assert_is_string, left_value, right_value)
            if guarded is not _TYPE_GUARD_OK:
                return guarded
        else:
            guarded = _type_guard(self.context, (self.left, self.right), "'+' operands must be numeric, strings, bytes or datetime", _assert_is_numeric, left_value, right_value)
            if guarded is not _TYPE_GUARD_OK:
                return guarded
        return operator.add(left_value, right_value)

class SubtractExpression(BinaryExpressionBase):
    """项目内部接口说明。"""
    compatible_types: tuple[_DataTypeDef, ...] = (DataType.FLOAT, DataType.DATETIME, DataType.TIMEDELTA)
    result_type: _DataTypeDef = DataType.UNDEFINED

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(SubtractExpression, self).__init__(*args, **kwargs)
        _assert_not_nullable(self.left.result_type, role="left operand of '-'")
        _assert_not_nullable(self.right.result_type, role="right operand of '-'")
        if self.left.result_type != DataType.UNDEFINED and self.right.result_type != DataType.UNDEFINED:
            if self.left.result_type == DataType.DATETIME:
                if self.right.result_type == DataType.DATETIME:
                    self.result_type = DataType.TIMEDELTA
                elif self.right.result_type == DataType.TIMEDELTA:
                    self.result_type = DataType.DATETIME
                else:
                    raise errors.EvaluationError('data type mismatch')
            elif self.left.result_type == DataType.TIMEDELTA:
                if self.right.result_type != DataType.TIMEDELTA:
                    raise errors.EvaluationError('data type mismatch')
                self.result_type = self.left.result_type
            elif self.left.result_type != self.right.result_type:
                raise errors.EvaluationError('data type mismatch')
            else:
                self.result_type = self.left.result_type

    def _op_sub(self, thing: Any) -> Any:
        left_value = self.left.evaluate(thing)
        if _is_unknown(left_value):
            return left_value
        right_value = self.right.evaluate(thing)
        if _is_unknown(right_value):
            return right_value
        if isinstance(left_value, datetime.datetime):
            if not isinstance(right_value, (datetime.datetime, datetime.timedelta)):
                reconciled = _reconcile_type_error(
                        self.context, self.left, self.right,
                        detail="right operand of '-' must be a datetime or timedelta"
                )
                if reconciled is not errors.UNDEFINED:
                    return reconciled
                raise errors.EvaluationError('data type mismatch (not a datetime or timedelta value)')
        elif isinstance(left_value, datetime.timedelta):
            if not isinstance(right_value, datetime.timedelta):
                reconciled = _reconcile_type_error(
                        self.context, self.left, self.right,
                        detail="right operand of '-' must be a timedelta"
                )
                if reconciled is not errors.UNDEFINED:
                    return reconciled
                raise errors.EvaluationError('data type mismatch (not a timedelta value)')
        else:
            guarded = _type_guard(self.context, (self.left, self.right), "'-' operands must be numeric, datetime or timedelta", _assert_is_numeric, left_value, right_value)
            if guarded is not _TYPE_GUARD_OK:
                return guarded
        return operator.sub(left_value, right_value)

class ArithmeticExpression(BinaryExpressionBase):
    """项目内部接口说明。"""
    compatible_types: tuple[_DataTypeDef, ...] = (DataType.FLOAT,)
    result_type: _DataTypeDef = DataType.FLOAT
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(ArithmeticExpression, self).__init__(*args, **kwargs)
        _assert_not_nullable(self.left.result_type, role='left arithmetic operand')
        _assert_not_nullable(self.right.result_type, role='right arithmetic operand')

    def __op_arithmetic(self, op: Callable[[Any, Any], Any], thing: Any) -> Any:
        left_value = self.left.evaluate(thing)
        if _is_unknown(left_value):
            return left_value
        right_value = self.right.evaluate(thing)
        if _is_unknown(right_value):
            return right_value
        guarded = _type_guard(
                self.context,
                (self.left, self.right),
                'arithmetic operands are not numeric',
                _assert_is_numeric,
                left_value,
                right_value
        )
        if guarded is not _TYPE_GUARD_OK:
            return guarded
        try:
            result = op(left_value, right_value)
        except ZeroDivisionError:
            raise errors.ArithmeticError('arithmetic error: division by zero') from None
        except ArithmeticError:
            raise errors.ArithmeticError('arithmetic error') from None
        return result

    _op_fdiv = functools.partialmethod(__op_arithmetic, operator.floordiv)
    _op_tdiv = functools.partialmethod(__op_arithmetic, operator.truediv)
    _op_mod  = functools.partialmethod(__op_arithmetic, operator.mod)
    _op_mul  = functools.partialmethod(__op_arithmetic, operator.mul)
    _op_pow  = functools.partialmethod(__op_arithmetic, operator.pow)

class BitwiseExpression(BinaryExpressionBase):
    """项目内部接口说明。"""
    compatible_types: tuple[_DataTypeDef, ...] = (DataType.FLOAT, DataType.SET)
    result_type: _DataTypeDef = DataType.UNDEFINED
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(BitwiseExpression, self).__init__(*args, **kwargs)
        _assert_not_nullable(self.left.result_type, role='left bitwise operand')
        _assert_not_nullable(self.right.result_type, role='right bitwise operand')
        # don't use DataType.is_compatible, because for sets the member type isn't important
        if self.left.result_type != DataType.UNDEFINED and self.right.result_type != DataType.UNDEFINED:
            if self.left.result_type.__class__ != self.right.result_type.__class__:
                raise errors.EvaluationError('data type mismatch')
        if self.left.result_type == DataType.FLOAT:
            if _is_reduced(self.left):
                _assert_is_natural_number(self.left.evaluate(None))
            self.result_type = DataType.FLOAT
        if self.right.result_type == DataType.FLOAT:
            if _is_reduced(self.right):
                _assert_is_natural_number(self.right.evaluate(None))
            self.result_type = DataType.FLOAT
        if DataType.is_type(self.left.result_type, DataType.SET) or DataType.is_type(self.right.result_type, DataType.SET):
            self.result_type = DataType.SET  # this discards the member type info

    def _op_bitwise(self, op: Callable[[Any, Any], Any], thing: Any) -> Any:
        left = self.left.evaluate(thing)
        if _is_unknown(left):
            return left
        left_type = DataType.from_value(left)
        if left_type == DataType.FLOAT:
            return self._op_bitwise_float(op, thing, left)
        elif DataType.is_type(left_type, DataType.SET):
            return self._op_bitwise_set(op, thing, left)
        reconciled = _reconcile_type_error(
                self.context, self.left, self.right,
                detail='bitwise operands must be integer numbers or sets'
        )
        if reconciled is not errors.UNDEFINED:
            return reconciled
        raise errors.EvaluationError('data type mismatch')

    def _op_bitwise_float(self, op: Callable[[Any, Any], Any], thing: Any, left: Any) -> Any:
        guarded = _type_guard(self.context, (self.left,), 'bitwise operand must be a natural number', _assert_is_natural_number, left)
        if guarded is not _TYPE_GUARD_OK:
            return guarded
        right = self.right.evaluate(thing)
        if _is_unknown(right):
            return right
        guarded = _type_guard(self.context, (self.left, self.right), 'bitwise operand must be a natural number', _assert_is_natural_number, left, right)
        if guarded is not _TYPE_GUARD_OK:
            return guarded
        return coerce_value(op(int(left), int(right)))

    def _op_bitwise_set(self, op: Callable[[Any, Any], Any], thing: Any, left: Any) -> Any:
        right = self.right.evaluate(thing)
        if _is_unknown(right):
            return right
        if not DataType.is_compatible(DataType.from_value(right), DataType.SET):
            reconciled = _reconcile_type_error(
                    self.context, self.left, self.right,
                    detail='set bitwise operands must both be sets'
            )
            if reconciled is not errors.UNDEFINED:
                return reconciled
            raise errors.EvaluationError('data type mismatch')
        # 集合中混入未知成员时交/并/对称差均不可确定：传播首个未知成员及其来源
        for collection in (left, right):
            pending = next((member for member in collection if _is_unknown(member)), None)
            if pending is not None:
                return pending
        return op(left, right)

    _op_bwand = functools.partialmethod(_op_bitwise, operator.and_)
    _op_bwor  = functools.partialmethod(_op_bitwise, operator.or_)
    _op_bwxor = functools.partialmethod(_op_bitwise, operator.xor)

class BitwiseShiftExpression(BitwiseExpression):
    compatible_types: tuple[_DataTypeDef, ...] = (DataType.FLOAT,)
    result_type: _DataTypeDef = DataType.FLOAT
    def _op_bitwise_shift(self, *args: Any, **kwargs: Any) -> Any:
        return self._op_bitwise(*args, **kwargs)
    _op_bwlsh = functools.partialmethod(_op_bitwise_shift, operator.lshift)
    _op_bwrsh = functools.partialmethod(_op_bitwise_shift, operator.rshift)
