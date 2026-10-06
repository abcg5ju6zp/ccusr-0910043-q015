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

## 未知值语义（三值逻辑）

默认情况下规则保持二值行为：缺失字段按 `Context.default_value` 兜底或抛出
`SymbolResolutionError`。通过 `Context(unknown_policy=...)` 可以为三类未知来源分别选择
`'propagate'`（传播为 UNKNOWN）、`'fallback'`（以 `default_value` 兜底，未配置时为 `null`）
或 `'abort'`（抛出异常，默认）：

- `'missing'`：字段缺失（符号 / 属性 / 键解析失败）
- `'parse_error'`：解析失败（自定义 resolver 抛出 `errors.DataParseError`）
- `'masked'`：受权限遮蔽（自定义 resolver 返回 `rule_engine.MASKED`）

传播时 `rule.evaluate()` 返回 `UnknownValue`（只携带来源类别与符号名，不含字段内容），
可用 `rule_engine.is_unknown()` 识别；`rule.matches()` / `rule.filter()` 把 UNKNOWN 视为非真。
所有运算符遵循同一真值表：

- `and` / `or` / `not` 采用 Kleene 三值逻辑（`false and UNKNOWN` 为 `false`，
  `true or UNKNOWN` 为 `true`，其余含 UNKNOWN 的组合传播 UNKNOWN）；
- 比较、算术、位运算、包含判断与函数调用对 UNKNOWN 严格传播（任一操作数未知则结果未知，
  函数不会被调用）；
- `??` 与对待 `null` 一样吸收 UNKNOWN，回退到右操作数；
- 条件位置（三元条件、推导式过滤、`matches` / `filter`）把 UNKNOWN 视为非真；
- 推导式中若入选元素的结果表达式为 UNKNOWN，则整个推导结果传播为 UNKNOWN。
