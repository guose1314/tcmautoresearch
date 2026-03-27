# src/research 与 src/llm 质量治理报告（2026-03-27）

## 1. 范围与目标

- 目标范围：`src/research/research_pipeline.py`、`src/llm/llm_engine.py`
- 治理维度：代码整洁、文档完整、测试覆盖、性能优化、安全编码
- 覆盖率目标：关键模块单元测试覆盖率 >= 90%

## 2. 关键改动摘要

### 2.1 代码整洁与结构稳定性

- 修复 `observe` 阶段 `clinical_gap_analysis` 为 `None` 时触发 `NoneType.get` 异常的问题。
- 在 `research_pipeline` 中引入可回退的 `LLMEngine` 符号绑定，保证临床 gap 测试可稳定 mock。
- 修复 `export_pipeline_data` 导出序列化问题：将 dataclass/Enum 转为 JSON 安全结构，避免导出失败。
- 清理导出符号定义，避免重复与歧义。

### 2.2 安全编码与性能约束

- 对观察阶段参数增加边界约束，降低异常输入导致资源放大的风险：
  - `literature_max_results` 限制为 `[1, 50]`
  - `max_texts` 限制为 `[1, 20]`
  - `max_chars_per_text` 限制为 `[200, 4000]`
- 导出路径写入保持 UTF-8，导出内容保持 JSON-safe，减少序列化异常外溢。

### 2.3 测试强化

- 新增 `tests/test_llm_engine.py`，覆盖：
  - Windows/Linux DLL 路径处理分支
  - 模型文件缺失、导入失败、重复加载、生成/卸载
  - 科研便捷方法与临床 gap 分析委托调用
- 新增 `tests/test_research_pipeline_quality.py`，覆盖：
  - 生命周期与阶段执行
  - 状态分支、异常分支、边界分支
  - 文献检索上限钳制、ingestion 分支、导出与清理分支

## 3. 覆盖率结果

覆盖率验证命令：使用项目测试运行器按模块收集覆盖率。

- `src/research/research_pipeline.py`: 90.1%
- `src/llm/llm_engine.py`: 95.6%

结论：关键模块覆盖率均达到 >= 90% 目标。

## 4. 风险与残余项

- `research_pipeline` 仍存在少量未覆盖分支，集中在防御性异常路径与低频分支，不影响主路径稳定性。
- `llm_engine` 未覆盖行主要为 Windows 特定目录过滤分支，对核心生成能力无阻断影响。

## 5. 后续建议（最多 3 条）

1. 在 CI 中固化这两个模块的覆盖率阈值门禁（<90% 直接失败）。
2. 对 `research_pipeline` 的低频异常分支补充更细粒度单测，持续提升分支覆盖率。
3. 补充安全专项测试：输入长度边界、配置污染、日志敏感信息泄露检查。
