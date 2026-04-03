# Stage 2 修复流程 (S2)

## 总体目标
将 Stage 1 达到的质量基线（整体评分 94.0 A级）进一步提升，重点治理代码健康度（code_health: 70.0 → 85.0+）

---

## 阶段结构 (S2-1 到 S2-6)

### S2-1: 预处理器模块优化（target: code_health +5）
**目标文件**: `src/preprocessor/document_preprocessor.py`
- 降低圈复杂度（目前最高）
- 补充类型注解（20%缺失）
- 提取辅助函数，单一职责

**关键指标**:
- 函数平均复杂度: 现状 7.2 → 目标 5.0
- 类型注解覆盖: 现状 76% → 目标 95%
- 单元测试覆盖: 现状 88% → 目标 95%

**执行命令**:
```powershell
[1] git checkout -b stage2-s2_1-preprocessor-opt
[2] python -m pylance mcp_s_pylanceInvokeRefactoring 
    --file src/preprocessor/document_preprocessor.py 
    --name source.addTypeAnnotation
[3] python tools/quality_gate.py
[4] git add -A && git commit -m "S2-1: 预处理器优化"
```

---

### S2-2: 抽取器模块重构（target: code_health +5）
**目标文件**: `src/extractors/advanced_entity_extractor.py`
- 分解大型方法（>15 行）
- 统一错误处理
- 补充文档字符串

**关键指标**:
- 最大方法长度: 现状 32 行 → 目标 15 行
- 异常覆盖: 现状 60% → 目标 100%
- 文档完整性: 现状 65% → 目标 95%

**执行命令**:
```powershell
[5] git checkout -b stage2-s2_2-extractor-refactor
[6] python -m pylance mcp_s_pylanceInvokeRefactoring 
    --file src/extractors/advanced_entity_extractor.py 
    --name source.fixAll.pylance
[7] python tools/quality_gate.py
[8] git add -A && git commit -m "S2-2: 抽取器重构"
```

---

### S2-3: 语义建模模块稳定化（target: code_health +5）
**目标文件**: `src/semantic_modeling/semantic_graph_builder.py`
- 消除重复逻辑
- 边界条件加固
- 性能优化

**关键指标**:
- 代码重复率: 现状 12% → 目标 < 5%
- 边界测试覆盖: 现状 70% → 目标 95%
- 响应时间: 现状 150ms → 目标 < 100ms

**执行命令**:
```powershell
[9] git checkout -b stage2-s2_3-semantic-stable
[10] python -m pylance mcp_s_pylanceInvokeRefactoring 
     --file src/semantic_modeling/semantic_graph_builder.py 
     --name source.fixAll.pylance
[11] python tools/quality_gate.py
[12] git add -A && git commit -m "S2-3: 语义建模稳定化"
```

---

### S2-4: 推理引擎优化（target: code_health +3）
**目标文件**: `src/reasoning/reasoning_engine.py`
- 函数幂等性验证
- 状态转换合法性检查
- 日志级别规范化

**关键指标**:
- 幂等性覆盖: 现状 80% → 目标 100%
- 状态无效转换拦截: 现状 85% → 目标 100%
- 日志规范: 现状 92% → 目标 100%

**执行命令**:
```powershell
[13] git checkout -b stage2-s2_4-reasoning-opt
[14] python -m pylance mcp_s_pylanceInvokeRefactoring 
     --file src/reasoning/reasoning_engine.py 
     --name source.fixAll.pylance
[15] python tools/quality_gate.py
[16] git add -A && git commit -m "S2-4: 推理引擎优化"
```

---

### S2-5: 输出生成器强化（target: code_health +4）
**目标文件**: `src/output/output_generator.py`
- 契约检查完整化
- 异常情况穷举
- 性能基准化

**关键指标**:
- 契约验证覆盖: 现状 78% → 目标 100%
- 异常路径: 现状 82% → 目标 100%
- 性能基准建立: 现状 缺失 → 目标 已建立

**执行命令**:
```powershell
[17] git checkout -b stage2-s2_5-output-strengthen
[18] python -m pylance mcp_s_pylanceInvokeRefactoring 
     --file src/output/output_generator.py 
     --name source.fixAll.pylance
[19] python tools/quality_gate.py
[20] git add -A && git commit -m "S2-5: 输出生成器强化"
```

---

### S2-6: 全量质量评估与合并（target: code_health 85.0+）
**验证**:
- 所有模块的质量指标汇聚
- 依赖图一致性检查
- 性能基准验证
- 回归测试全通过

**执行命令**:
```powershell
[21] git checkout main
[22] git merge stage2-s2_1-preprocessor-opt
[23] git merge stage2-s2_2-extractor-refactor
[24] git merge stage2-s2_3-semantic-stable
[25] git merge stage2-s2_4-reasoning-opt
[26] git merge stage2-s2_5-output-strengthen
[27] python tools/quality_gate.py
[28] python tools/quality_assessment.py --gates-report output/quality-gate.json
[29] python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json
[30] python tools/quality_improvement_archive.py
[31] python tools/quality_feedback.py
[32] git add -A && git commit -m "S2-6: Stage 2 完成，质量评分合并"
```

---

## 预期成果

| 维度 | Stage 1 | Stage 2 目标 | 提升幅度 |
|------|---------|-----------|--------|
| code_health | 70.0 | 85.0+ | +15.0 |
| gate_stability | 100.0 | 100.0 | - |
| test_reliability | 100.0 | 100.0 | - |
| logic_health | 100.0 | 100.0 | - |
| architecture_health | 100.0 | 100.0 | - |
| **overall_score** | **94.0** | **96.0+** | **+2.0** |
| **grade** | **A** | **A+** | - |

---

## 失败恢复策略

每个 S2-x 阶段如果失败：
1. 查看 `logs/stage2/stage2_Sx_*.log` 日志
2. 运行 `git restore .` 清理未提交的更改
3. 检查具体的代码质量告警并手动修复
4. 重新运行该阶段

---

## 版本管理

- **分支策略**: 每个 S2-x 创建独立分支，完成后 merge 回 stage2-integration
- **标签**: 每个阶段完成后打标签 `stage2-s2_x-complete`
- **提交消息**: 统一格式 `S2-x: 模块名-优化方向`

