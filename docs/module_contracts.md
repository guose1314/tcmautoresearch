# 模块契约文档

本文档定义全应用的模块职责边界、流程规范、依赖方向、安全约束与性能优化点。

## 1. 分层结构

- L1 核心层: src/core
- L2 处理层: src/preprocessor, src/extractors, src/semantic_modeling, src/reasoning, src/output, src/learning
- L3 流程层: src/cycle, src/research
- L4 测试层: tests, integration_tests

依赖规则:
- 低层不能反向依赖高层。
- 业务代码 (src/) 不强依赖测试框架。
- 重量级依赖 (如 llama-cpp-python) 必须延迟导入。

## 2. 模块职责与接口

| 模块 | 主要职责 | 输入 | 输出 | 关键依赖 | 安全与性能约束 |
|---|---|---|---|---|---|
| src/core/module_base.py | 统一生命周期与执行指标 | context(dict) | result(dict) | logging, concurrent.futures | 全局线程池复用，避免资源泄漏 |
| src/core/architecture.py | 模块注册、依赖图、健康状态 | ModuleInfo | registry state | networkx | 只维护架构与注册，不重复定义接口类型 |
| src/core/module_interface.py | 标准接口与上下文/输出数据结构 | ModuleContext | ModuleOutput | dataclasses | 作为接口单一事实来源 |
| src/preprocessor/document_preprocessor.py | 文本清洗、繁简转换、分词 | raw_text(str) | processed_text, metadata | jieba/opencc(可选) | 输入类型校验、长度上限、控制字符清洗 |
| src/extractors/advanced_entity_extractor.py | 中医术语实体抽取 | processed_text | entities/statistics | tcm_lexicon | 使用词典驱动抽取，避免硬编码规则发散 |
| src/semantic_modeling/semantic_graph_builder.py | 语义图构建与研究视角分析 | entities | semantic_graph | networkx | 图规模受控，避免无上限节点增长 |
| src/reasoning/reasoning_engine.py | 关系推理与模式识别 | entities, graph | reasoning results | networkx | 输出结构化，避免返回不可序列化对象 |
| src/output/output_generator.py | 最终结构化结果组装 | pipeline context | structured_json | BaseModule | 路径脱敏、列表限长、JSON 安全化 |
| src/cycle/iteration_cycle.py | 生成-测试-修复主循环 | context | IterationResult | core.get_global_executor | 使用共享线程池，减少线程创建开销 |
| src/cycle/test_driven_iteration.py | 测试驱动迭代管理 | test suite/context | TestResult list | unittest (pytest可选) | pytest 仅可选加载，防止运行时硬依赖 |
| src/research/research_pipeline.py | 科研闭环编排 | cycle context | phase outputs | preprocessor/extractor/LLM | LLMEngine 延迟导入，降低模块导入副作用 |
| src/llm/llm_engine.py | 本地 GGUF 推理与科研提示词编排 | prompt/system_prompt | model response | llama-cpp-python | 导入失败可诊断、模型路径校验、GPU 参数受控 |

## 3. 流程规范

标准流水线:
1. 输入校验
2. 预处理
3. 抽取
4. 建模
5. 推理
6. 输出
7. 质量指标计算

约束:
- 每一阶段必须返回结构化 dict。
- 异常必须记录日志并保留最小可诊断信息。
- 关键路径必须可在无 GPU 环境下完成基础流程。

## 4. 安全编码规范

- 不信任外部输入: 类型、长度、内容均需校验。
- 不暴露敏感路径: 输出元数据仅保留 basename。
- 不传播不可序列化对象: 输出前统一 JSON-safe 转换。
- 不在业务模块中强依赖测试框架与调试依赖。

## 5. 性能优化规范

- 正则预编译，减少高频调用开销。
- 共享线程池复用，避免线程频繁创建/销毁。
- 大列表输出裁剪上限，控制内存与序列化耗时。
- 深层对象输出限制递归深度，防止深度爆炸。

## 6. 测试与覆盖率标准

- 核心关键路径模块（core/preprocessor/output/cycle）单元测试覆盖率目标: >= 90%。
- 关键治理模块（research_pipeline/llm_engine）单元测试覆盖率目标: >= 90%。
- 每次重构后必须执行覆盖率测试与语法检查。
- 覆盖率未达标时不得合并重构分支。
