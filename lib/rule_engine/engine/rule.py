#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  rule_engine/engine/rule.py
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

import decimal
from typing import Any, Iterable, Iterator, TYPE_CHECKING, NamedTuple

from .. import errors
from ..parser import Parser
from ..unknown import UnknownValue
from .context import Context

if TYPE_CHECKING:
    import graphviz

class TernaryResult(NamedTuple):
    """规则的三值求值结果。

    .. py:attribute:: match

       ``True`` / ``False`` 为明确结论；``None`` 表示结论未知（存在传播到根的未知值）。

    .. py:attribute:: unknowns

       导致结论未知的全部未知值，按出现顺序去重；只含来源与原因，不含字段内容。
    """
    match: bool | None
    unknowns: tuple[UnknownValue, ...]

    def explain(self) -> list[dict[str, Any]]:
        """返回可安全记录 / 回传给客服的未知来源说明列表。"""
        return [unknown.explain() for unknown in self.unknowns]

class Rule(object):
    """项目内部接口说明。"""
    parser: Parser = Parser()
    """
    The :py:class:`~rule_engine.parser.Parser` instance that will be used for parsing the rule text into a compatible
    用于规则求值的抽象语法树（AST）。
    """
    def __init__(self, text: str, context: Context | None = None) -> None:
        """项目内部接口说明。"""
        context = context or Context()
        self.text = text
        self.context = context
        self.statement = self.parser.parse(text, context)

    def __getstate__(self) -> dict[str, Any]:
        return {'text': self.text, 'context': self.context}

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.text = state['text']
        self.context = state['context']
        self.statement = self.parser.parse(self.text, self.context)

    def __repr__(self) -> str:
        return "<{0} text={1!r} >".format(self.__class__.__name__, self.text)

    def __str__(self) -> str:
        return self.text

    def filter(self, things: Iterable[Any]) -> Iterator[Any]:
        """项目内部接口说明。"""
        # 未知结论一律不进入“符合条件”集合
        yield from (thing for thing in things if self.matches(thing))

    @classmethod
    def is_valid(cls, text: str, context: Context | None = None) -> bool:
        """项目内部接口说明。"""
        try:
            cls.parser.parse(text, (context or Context()))
        except errors.EngineError:
            return False
        return True

    def evaluate(self, thing: Any) -> Any:
        """项目内部接口说明。"""
        self.context._tls.reset()
        with decimal.localcontext(self.context.decimal_context):
            return self.statement.evaluate(thing)

    def evaluate_ternary(self, thing: Any) -> TernaryResult:
        """三值求值：返回 :py:class:`TernaryResult`。

        仅当根表达式求值为未知值（未知沿逻辑链一路传播到结论）时，
        :py:attr:`~TernaryResult.match` 才为 ``None``。集合 / 推导结果中的未知成员属于数据本身，
        不改变根结论；调用方仍可通过 :py:meth:`evaluate` 取回其中保留的未知来源。

        旧规则（上下文无 :py:class:`~rule_engine.unknown.UnknownPolicy`）只会得到明确的布尔结论。
        """
        result = self.evaluate(thing)
        if isinstance(result, UnknownValue):
            return TernaryResult(None, (result,))
        return TernaryResult(bool(result), ())

    def matches(self, thing: Any) -> bool:
        """二值判定（向后兼容）。

        配置了传播型策略时，未知结论会被压成 ``False``；需要区分“不符合”与“资料未到齐”的调用方
        请改用 :py:meth:`evaluate_ternary`。
        """
        result = self.evaluate(thing)
        if isinstance(result, UnknownValue):
            return False
        return bool(result)

    def to_graphviz(self) -> 'graphviz.Digraph':
        """项目内部接口说明。"""
        import graphviz
        digraph = graphviz.Digraph(comment=self.text)
        self.statement.to_graphviz(digraph)
        return digraph

class DebugRule(Rule):
    parser: Parser  # set per-instance in __init__ (overrides the class-level attribute on Rule)
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.parser = Parser(debug=True)
        super(DebugRule, self).__init__(*args, **kwargs)
