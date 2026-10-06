# 规则表达式引擎

本项目提供可嵌入服务端的规则解析、类型检查、属性解析和表达式评估能力。生产源码位于 `lib/rule_engine/`，核心回归测试位于 `tests/`。

## 安装

`python3 -m pip install --break-system-packages --no-build-isolation -e .`

## 测试

`python3 -m pytest -q`

## 构建

`python3 -m compileall -q lib/rule_engine`

`python3 -m build --wheel --no-isolation`

## 使用

调用方创建规则并传入普通 Python 对象即可完成本地评估，不需要外部服务。

### 未知值（三值逻辑）

默认情况下引擎维持历史二值行为：字段缺失或类型不符会抛出异常或按 `default_value` 处理，规则结论只有真/假。

资格服务可通过 `Context(unknown_policy=...)` 开启可组合的未知值语义，把三类“资料尚未到齐”的情况与明确的假值区分开：

| 原因 `UnknownReason` | 含义 |
| --- | --- |
| `MISSING` | 字段 / 键缺失 |
| `PARSE_ERROR` | 字段存在但无法解析为目标类型（或与运算不兼容） |
| `MASKED` | 字段受权限遮蔽（由 resolver 或自定义函数显式上报） |

每种原因可独立选择处置 `UnknownAction`：`PROPAGATE`（按 Kleene 三值真值表传播）、
`(DEFAULT, value)`（以给定值兜底）、`ABORT`（抛出 `UnknownAbortError` 中止求值）。

```python
from rule_engine import Rule, Context, UnknownPolicy, UnknownAction, UnknownReason, UnknownValue

# 缺失则传播（资料未到齐，待补件）；解析失败中止（数据质量告警）；受遮蔽按“已核验”兜底
policy = UnknownPolicy(
    missing=UnknownAction.PROPAGATE,
    parse_error=UnknownAction.ABORT,
    masked=(UnknownAction.DEFAULT, True),
)
context = Context(unknown_policy=policy)

result = Rule('age >= 18 and has_docs == true', context=context).evaluate_ternary(application)
# result.match: True / False 为明确结论；None 表示因未知值无法判定
# result.explain(): [{'reason': 'missing', 'source': 'age', 'detail': None}]  —— 只含来源，不含字段内容
```

三值真值表对布尔短路、比较、正则、算术、`in`、集合推导、三元、`??` 默认值、自定义函数及
`$any`/`$all`/`$sum`/`$min`/`$max` 统一生效；`??` 可为未知值兜底，`matches()` 仍返回纯布尔
（未知结论压成 `False`）。旧规则不设置策略时行为完全不变。

