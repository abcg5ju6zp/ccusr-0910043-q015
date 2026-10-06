"""运行项目 README 声明的核心回归测试。"""

from importlib import import_module


engine = import_module("tests.engine")
parser = import_module("tests.parser")
thread_safety = import_module("tests.thread_safety")
unknown = import_module("tests.unknown")


EngineTests = engine.EngineTests
EngineRuleTests = engine.EngineRuleTests
EngineDatetimeRuleTests = engine.EngineDatetimeRuleTests
ContextTests = engine.ContextTests
ObjectTypeTests = engine.ObjectTypeTests
ContextSerializationTests = engine.ContextSerializationTests
ParserTests = parser.ParserTests
ParserLeftOperatorRightTests = parser.ParserLeftOperatorRightTests
ParserLiteralTests = parser.ParserLiteralTests
ThreadSafetyTests = thread_safety.ThreadSafetyTests
UnknownPolicyTests = unknown.UnknownPolicyTests
UnknownValueTests = unknown.UnknownValueTests
UnknownDefaultCompatTests = unknown.UnknownDefaultCompatTests
UnknownMissingTests = unknown.UnknownMissingTests
UnknownParseErrorTests = unknown.UnknownParseErrorTests
UnknownMaskedTests = unknown.UnknownMaskedTests
UnknownTruthTableTests = unknown.UnknownTruthTableTests
UnknownComprehensionTests = unknown.UnknownComprehensionTests
UnknownFunctionCallTests = unknown.UnknownFunctionCallTests
UnknownProvenanceTests = unknown.UnknownProvenanceTests
UnknownSerializationTests = unknown.UnknownSerializationTests
