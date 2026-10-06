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

"""可组合的未知值（三值逻辑）语义支持。

本模块实现规则引擎的三值逻辑基础设施：当字段缺失、解析失败或受权限遮蔽时，
调用方可以通过 :py:class:`UnknownPolicy` 为每类来源分别选择传播（``'propagate'``）、
兜底（``'fallback'``）或中止（``'abort'``）。传播时求值产生 :py:class:`UnknownValue`，
它只携带来源类别与符号名（不暴露字段内容），并遵循统一的真值表在表达式中流动。
"""

import collections.abc
import enum
from typing import Any

class UnknownSource(enum.Enum):
    """未知值的来源类别。"""
    MISSING = 'missing'
    """字段缺失：符号、属性或键在求值对象上不存在。"""
    PARSE_ERROR = 'parse_error'
    """解析失败：字段存在但解析器无法将其解析为可用值。"""
    MASKED = 'masked'
    """受权限遮蔽：调用方无权查看该字段的值。"""

class UnknownValue(object):
    """三值逻辑中的 UNKNOWN 值。

    仅保留来源（:py:attr:`source`）与符号名（:py:attr:`symbol`）以便定位信息在哪一步丢失，
    不携带字段内容。UNKNOWN 在布尔上下文中为假（条件位置视为"非真"），调用方应使用
    :py:func:`is_unknown` 将其与普通的 ``False`` 区分开。
    """
    __slots__ = ('source', 'symbol')
    def __init__(self, source: UnknownSource, symbol: str | None = None) -> None:
        if not isinstance(source, UnknownSource):
            raise TypeError('source must be an UnknownSource, not ' + type(source).__name__)
        self.source = source
        """未知的来源类别（:py:class:`UnknownSource` 成员）。"""
        self.symbol = symbol
        """丢失信息的符号/属性/键名；不适用时为 ``None``。不包含字段内容。"""

    def __bool__(self) -> bool:
        # 条件位置（matches/filter、三元条件、推导式过滤）将 UNKNOWN 视为"非真"
        return False

    def __eq__(self, other: Any) -> bool:
        # Python 层面的相等仅用于检查来源信息；引擎内部的比较运算遵循三值真值表，不会走到这里
        if not isinstance(other, UnknownValue):
            return NotImplemented
        return self.source is other.source and self.symbol == other.symbol

    def __hash__(self) -> int:
        return hash((UnknownValue, self.source, self.symbol))

    def __repr__(self) -> str:
        return "<{0} source={1!r} symbol={2!r} >".format(self.__class__.__name__, self.source, self.symbol)

def is_unknown(value: Any) -> bool:
    """判断 *value* 是否为三值逻辑中的 UNKNOWN。"""
    return isinstance(value, UnknownValue)

def first_unknown(*values: Any) -> UnknownValue | None:
    """返回参数中第一个 UNKNOWN 值（保留最早的来源信息），没有则返回 ``None``。"""
    for value in values:
        if isinstance(value, UnknownValue):
            return value
    return None

class _Masked(object):
    """resolver 可返回的哨兵值，表示字段受权限遮蔽。"""
    def __bool__(self) -> bool:
        return False
    __name__ = 'MASKED'
    __nonzero__ = __bool__
    def __reduce__(self) -> str:
        # pickle by reference so the singleton identity survives pickling
        return 'MASKED'
    def __repr__(self) -> str:
        return self.__name__
MASKED = _Masked()
"""
哨兵值：自定义 resolver 返回它表示对应字段受权限遮蔽、不可见。
引擎随后按 ``unknown_policy`` 的 ``'masked'`` 动作处理（传播 / 兜底 / 中止）。
"""

class UnknownPolicy(object):
    """未知值处理策略：为每类 :py:class:`UnknownSource` 指定动作。

    动作取值：

    * ``'abort'`` —— 中止：抛出对应异常（默认行为，旧规则维持二值结果）。
    * ``'fallback'`` —— 兜底：以 ``Context.default_value``（未配置时为 ``null``）替代。
    * ``'propagate'`` —— 传播：产生 :py:class:`UnknownValue` 并沿表达式按真值表流动。

    属性值为 ``None`` 表示该来源未显式配置，由引擎按历史默认决定
    （例如字段缺失在配置了 ``default_value`` 时默认兜底，否则中止）。
    """
    __slots__ = ('missing', 'parse_error', 'masked')
    ACTIONS = ('abort', 'fallback', 'propagate')
    """合法的动作取值。"""
    SOURCES = ('missing', 'parse_error', 'masked')
    """可配置的来源名称（与 :py:class:`UnknownSource` 的 ``value`` 一致）。"""
    def __init__(
                    self,
                    missing: str | None = None,
                    parse_error: str | None = None,
                    masked: str | None = None
    ) -> None:
        for name, action in (('missing', missing), ('parse_error', parse_error), ('masked', masked)):
            if action is not None and action not in self.ACTIONS:
                raise ValueError("invalid unknown policy action for {0!r}: {1!r}".format(name, action))
        self.missing = missing
        self.parse_error = parse_error
        self.masked = masked

    def __repr__(self) -> str:
        return "<{0} missing={1!r} parse_error={2!r} masked={3!r} >".format(
                self.__class__.__name__, self.missing, self.parse_error, self.masked
        )

    def action_for(self, source: UnknownSource) -> str | None:
        """返回 *source* 显式配置的动作；未配置时返回 ``None``。"""
        return getattr(self, source.value)

    @classmethod
    def from_value(cls, value: 'UnknownPolicy | str | collections.abc.Mapping[str, str] | None') -> 'UnknownPolicy':
        """从用户配置构造策略。

        接受 ``None``（全部未配置）、单个动作字符串（三类来源共用）、映射
        （按来源分别指定，键为 ``'missing'`` / ``'parse_error'`` / ``'masked'``）
        或已有的 :py:class:`UnknownPolicy` 实例。
        """
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(missing=value, parse_error=value, masked=value)
        if isinstance(value, collections.abc.Mapping):
            unknown_keys = set(value.keys()) - set(cls.SOURCES)
            if unknown_keys:
                raise ValueError('invalid unknown policy source(s): ' + ', '.join(sorted(unknown_keys)))
            return cls(
                    missing=value.get('missing'),
                    parse_error=value.get('parse_error'),
                    masked=value.get('masked')
            )
        raise TypeError('invalid unknown_policy type: ' + type(value).__name__)
