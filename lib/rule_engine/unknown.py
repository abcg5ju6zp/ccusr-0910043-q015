#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  rule_engine/unknown.py
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

"""可组合的未知值（三值逻辑）语义。

字段缺失（:py:class:`UnknownReason.MISSING`）、解析失败
（:py:class:`UnknownReason.PARSE_ERROR`）和受权限遮蔽
（:py:class:`UnknownReason.MASKED`）不再被压成普通的 ``False``，而是以
:py:class:`UnknownValue` 在表达式中传播。调用方通过 :py:class:`UnknownPolicy`
按原因分别选择三种处置：

* :py:class:`UnknownAction.PROPAGATE` —— 未知值沿表达式继续传播（三值逻辑）；
* :py:class:`UnknownAction.DEFAULT` —— 立即以调用方给定的兜底值替换；
* :py:class:`UnknownAction.ABORT` —— 抛出 :py:class:`~rule_engine.errors.UnknownAbortError` 中止求值。

未知值只携带**来源路径**与**原因**，不携带字段内容，因此可以安全地写入日志或回传给客服系统。
"""

from __future__ import annotations

import enum
from typing import Any, Iterator, Mapping, Sequence

from .errors import UnknownAbortError, UnknownFieldError

__all__ = (
        'UnknownAction',
        'UnknownPolicy',
        'UnknownReason',
        'UnknownValue',
        'is_unknown',
        'logic_and',
        'logic_not',
        'logic_or',
        'merge_unknowns',
        'tribool',
)

class UnknownReason(str, enum.Enum):
    """未知值的产生原因。"""
    MISSING = 'missing'
    """字段或键缺失（解析时不存在）。"""
    PARSE_ERROR = 'parse_error'
    """字段存在但值无法解析为目标类型。"""
    MASKED = 'masked'
    """字段存在但调用方因权限等原因主动遮蔽，不允许读取内容。"""

class UnknownAction(str, enum.Enum):
    """遇到某类未知值时采取的处置动作。"""
    PROPAGATE = 'propagate'
    """以三值逻辑继续传播 :py:class:`UnknownValue`。"""
    DEFAULT = 'default'
    """使用策略中为该原因配置的兜底值。"""
    ABORT = 'abort'
    """抛出 :py:class:`~rule_engine.errors.UnknownAbortError` 中止求值。"""

class UnknownValue(object):
    """表达式求值过程中的未知值。

    实例是不可变的；:py:attr:`source` 只记录规则侧的属性名 / 键名等路径片段，
    :py:attr:`detail` 只能是不含字段内容的说明文字。
    """
    __slots__ = ('_reason', '_source', '_detail')

    def __init__(
            self,
            reason: UnknownReason,
            *,
            source: Sequence[str] | None = None,
            detail: str | None = None
    ) -> None:
        self._reason = UnknownReason(reason)
        self._source: tuple[str, ...] = tuple(part for part in (source or ()) if part)
        self._detail = detail

    def __repr__(self) -> str:
        return "<{} reason={!r} source={!r}>".format(self.__class__.__name__, self._reason.value, self._source)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, UnknownValue):
            return NotImplemented
        return self._reason == other._reason and self._source == other._source and self._detail == other._detail

    def __ne__(self, other: Any) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        return hash((self._reason, self._source, self._detail))

    def __bool__(self) -> bool:
        # 显式拒绝被静默压成 False：三值逻辑必须经过真值表函数或 Rule 层的三态裁决。
        raise TypeError('UnknownValue has no boolean truth value; handle it via the unknown value truth table')

    __nonzero__ = __bool__

    @property
    def reason(self) -> UnknownReason:
        """未知值的产生原因。"""
        return self._reason

    @property
    def source(self) -> tuple[str, ...]:
        """未知来源路径（规则侧名称，不含任何字段数据）。"""
        return self._source

    @property
    def detail(self) -> str | None:
        """可选的、不包含字段内容的说明文字。"""
        return self._detail

    def derive(self, *source: str | None) -> 'UnknownValue':
        """返回在来源路径后追加 *source* 片段的新未知值（原因与说明保持不变）。"""
        extended = self._source + tuple(part for part in source if part)
        return UnknownValue(self._reason, source=extended, detail=self._detail)

    def explain(self) -> dict[str, Any]:
        """返回可安全记录 / 回传的结构化来源说明（不含字段内容）。"""
        return {'reason': self._reason.value, 'source': '.'.join(self._source) if self._source else None, 'detail': self._detail}

    @classmethod
    def from_error(cls, error: UnknownFieldError) -> 'UnknownValue':
        """从 :py:class:`~rule_engine.errors.UnknownFieldError` 构造未知值。"""
        return cls(error.reason, source=error.source, detail=error.detail)

def is_unknown(value: Any) -> bool:
    """判断 *value* 是否为 :py:class:`UnknownValue`。"""
    return isinstance(value, UnknownValue)

def tribool(value: Any) -> str:
    """把求值结果归类为三值：``'t'``（真）、``'f'``（假）或 ``'u'``（未知）。

    非布尔值沿用 Python 的真值判定（空集合 / 0 / 空串为假），与历史规则语义一致。
    """
    if isinstance(value, UnknownValue):
        return 'u'
    return 't' if bool(value) else 'f'

def logic_and(left: Any, right: Any) -> Any:
    """Kleene 合取真值表：任一方明确为假即为假；否则任一方未知即为未知。"""
    ls, rs = tribool(left), tribool(right)
    if ls == 'f' or rs == 'f':
        return False
    if ls == 'u':
        return left
    if rs == 'u':
        return right
    return True

def logic_or(left: Any, right: Any) -> Any:
    """Kleene 析取真值表：任一方明确为真即为真；否则任一方未知即为未知。"""
    ls, rs = tribool(left), tribool(right)
    if ls == 't' or rs == 't':
        return True
    if ls == 'u':
        return left
    if rs == 'u':
        return right
    return False

def logic_not(value: Any) -> Any:
    """Kleene 否定：未知的否定仍是未知。"""
    if isinstance(value, UnknownValue):
        return value
    return not bool(value)

def merge_unknowns(*values: Any) -> UnknownValue | None:
    """在若干求值结果中收集未知值并合并来源；没有未知值时返回 ``None``。"""
    merged: UnknownValue | None = None
    for value in values:
        for unknown in _iter_unknowns(value):
            if merged is None:
                merged = unknown
            elif unknown.reason != merged.reason:
                # 原因不同无法归并时，保留先出现的，但把来源合并进来以便客服定位整条链路。
                merged = UnknownValue(merged.reason, source=merged.source + unknown.source, detail=merged.detail)
            else:
                merged = UnknownValue(
                        merged.reason,
                        source=tuple(dict.fromkeys(merged.source + unknown.source)),
                        detail=merged.detail or unknown.detail
                )
    return merged

def _iter_unknowns(value: Any) -> Iterator[UnknownValue]:
    if isinstance(value, UnknownValue):
        yield value
        return
    # 数组（tuple）、集合（set/frozenset）与映射中的未知成员同样需要参与来源归并。
    if isinstance(value, (tuple, list, set, frozenset)):
        for member in value:
            yield from _iter_unknowns(member)
    elif isinstance(value, Mapping):
        for member in value.values():
            yield from _iter_unknowns(member)

_SpecType = UnknownAction | tuple[UnknownAction, Any]

class UnknownPolicy(object):
    """按未知原因组合的处置策略。

    每个原因接受一个 :py:class:`UnknownAction`，或 ``(action, fallback)`` 二元组；
    当动作为 :py:class:`UnknownAction.DEFAULT` 时必须提供兜底值。
    """
    def __init__(
            self,
            *,
            missing: _SpecType = UnknownAction.PROPAGATE,
            parse_error: _SpecType = UnknownAction.PROPAGATE,
            masked: _SpecType = UnknownAction.PROPAGATE
    ) -> None:
        self._actions: dict[UnknownReason, UnknownAction] = {}
        self._defaults: dict[UnknownReason, Any] = {}
        for reason, spec in ((UnknownReason.MISSING, missing), (UnknownReason.PARSE_ERROR, parse_error), (UnknownReason.MASKED, masked)):
            if isinstance(spec, tuple):
                action, fallback = spec
                action = UnknownAction(action)
                if action is not UnknownAction.DEFAULT:
                    raise ValueError("a fallback value may only be given together with UnknownAction.DEFAULT ({0})".format(reason.value))
                self._actions[reason] = action
                self._defaults[reason] = fallback
            else:
                action = UnknownAction(spec)
                if action is UnknownAction.DEFAULT:
                    raise ValueError("action DEFAULT for {0!r} requires a fallback value, use (UnknownAction.DEFAULT, value)".format(reason.value))
                self._actions[reason] = action

    def __repr__(self) -> str:
        return "<{} actions={!r}>".format(self.__class__.__name__, {reason.value: action.value for reason, action in self._actions.items()})

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, UnknownPolicy):
            return NotImplemented
        return self._actions == other._actions and all(
                self._defaults.get(reason) == other._defaults.get(reason) for reason in UnknownReason
        )

    def action_for(self, reason: UnknownReason) -> UnknownAction:
        """返回 *reason* 配置的动作。"""
        return self._actions[UnknownReason(reason)]

    def resolve(self, unknown: UnknownValue) -> Any:
        """按策略裁决一个未知值。

        :return: 传播时原样返回 :py:class:`UnknownValue`；兜底时返回兜底值；中止时抛出异常。
        """
        reason = unknown.reason
        action = self._actions[reason]
        if action is UnknownAction.PROPAGATE:
            return unknown
        if action is UnknownAction.DEFAULT:
            return self._defaults[reason]
        raise UnknownAbortError(unknown)

    def resolve_error(self, error: UnknownFieldError) -> Any:
        """便捷方法：先把 :py:class:`~rule_engine.errors.UnknownFieldError` 转成未知值再裁决。"""
        return self.resolve(UnknownValue.from_error(error))

    @classmethod
    def propagate_all(cls) -> 'UnknownPolicy':
        """三类未知值全部传播（完整三值逻辑）。"""
        return cls()

    @classmethod
    def abort_all(cls) -> 'UnknownPolicy':
        """三类未知值全部中止求值。"""
        return cls(
                missing=UnknownAction.ABORT,
                parse_error=UnknownAction.ABORT,
                masked=UnknownAction.ABORT
        )

    @classmethod
    def binary(cls, fallback: Any = False) -> 'UnknownPolicy':
        """三类未知值统一压成同一个二值兜底（默认 ``False``）。

        这显式复刻了资格服务过去“缺字段即不符合”的二值行为，便于灰度切换。
        """
        return cls(
                missing=(UnknownAction.DEFAULT, fallback),
                parse_error=(UnknownAction.DEFAULT, fallback),
                masked=(UnknownAction.DEFAULT, fallback)
        )
