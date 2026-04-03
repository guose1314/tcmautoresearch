# Stage 2 修复流程详细表 (S2-1 ~ S2-6)

## 流程图（ASCII）

```
┌─────────────────────────────────────────────────────────────────┐
│              Stage 2 质量优化全流程 (代码健康度提升)             │
└─────────────────────────────────────────────────────────────────┘

        ┌─────────────────────────────────────────────────────┐
        │  S2-1: 预处理器模块优化 (code_health +5)           │
        │  ┌───────────────────────────────────────────────┐  │
        │  │ 1. 创建分支 stage2-s2_1-preprocessor-opt     │  │
        │  │ 2. 添加类型注解 (76% → 95%)                  │  │
        │  │ 3. 应用Pylance自动修复                       │  │
        │  │ 4. 运行品质门 (target: code_health > 75)   │  │
        │  │ 5. 提交: S2-1-complete                       │  │
        │  └───────────────────────────────────────────────┘  │
        └──────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────▼──────────────────────────────────┐
        │  S2-2: 抽取器模块重构 (code_health +5)            │
        │  ┌───────────────────────────────────────────────┐  │
        │  │ 6. 创建分支 stage2-s2_2-extractor-refactor   │  │
        │  │ 7. 分解大型方法 (32 lines → 15 lines)       │  │
        │  │ 8. 统一错误处理 (60% → 100%)                │  │
        │  │ 9. 运行品质门 (target: code_health > 80)   │  │
        │  │10. 提交: S2-2-complete                       │  │
        │  └───────────────────────────────────────────────┘  │
        └──────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────▼──────────────────────────────────┐
        │  S2-3: 语义建模模块稳定化 (code_health +5)        │
        │  ┌───────────────────────────────────────────────┐  │
        │  │11. 创建分支 stage2-s2_3-semantic-stable      │  │
        │  │12. 消除重复逻辑 (12% → < 5%)               │  │
        │  │13. 加固边界条件 (70% → 95%)                 │  │
        │  │14. 运行品质门 (target: code_health > 80)   │  │
        │  │15. 提交: S2-3-complete                       │  │
        │  └───────────────────────────────────────────────┘  │
        └──────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────▼──────────────────────────────────┐
        │  S2-4: 推理引擎优化 (code_health +3)              │
        │  ┌───────────────────────────────────────────────┐  │
        │  │16. 创建分支 stage2-s2_4-reasoning-opt        │  │
        │  │17. 函数幂等性验证 (80% → 100%)              │  │
        │  │18. 状态转换合法性 (85% → 100%)              │  │
        │  │19. 运行品质门 (target: code_health > 81)   │  │
        │  │20. 提交: S2-4-complete                       │  │
        │  └───────────────────────────────────────────────┘  │
        └──────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────▼──────────────────────────────────┐
        │  S2-5: 输出生成器强化 (code_health +4)           │
        │  ┌───────────────────────────────────────────────┐  │
        │  │21. 创建分支 stage2-s2_5-output-strengthen   │  │
        │  │22. 契约检查完整化 (78% → 100%)              │  │
        │  │23. 异常情况穷举 (82% → 100%)                │  │
        │  │24. 运行品质门 (target: code_health > 85)   │  │
        │  │25. 提交: S2-5-complete                       │  │
        │  └───────────────────────────────────────────────┘  │
        └──────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────▼──────────────────────────────────┐
        │  S2-6: 质量评估与合并 (overall +2)               │
        │  ┌───────────────────────────────────────────────┐  │
        │  │26. 验证所有分支合并                          │  │
        │  │27. 全量品质门测试                            │  │
        │  │28. 品质评估汇总 (target: > 96.0)           │  │
        │  │29. 持续改进循环                              │  │
        │  │30. 存档质量指标                              │  │
        │  │31. 结果反馈生成                              │  │
        │  │32. 最终提交: S2-6-complete                   │  │
        │  └───────────────────────────────────────────────┘  │
        └──────────────────┬──────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  ✓ 完成     │ code_health: 85.0+
                    │ overall: 96.0+│ grade: A+
                    └─────────────┘
```

---

## 详细执行步骤表

### 第一行：S2-1 预处理器模块优化

| 步骤 | 命令编号 | 操作 | 命令 | 预期结果 | 失败恢复 |
|------|---------|------|------|--------|--------|
| 1 | [1] | 创建分支 | `git checkout -b stage2-s2_1-preprocessor-opt` | 分支创建成功 | `git branch -D stage2-s2_1-preprocessor-opt` |
| 2 | [2] | 添加类型注解 | `python -m pylance mcp_s_pylanceInvokeRefactoring --file src/preprocessor/document_preprocessor.py --name source.addTypeAnnotation` | 注解补充 76% → 90%+ | `git restore src/preprocessor/` |
| 3 | [3] | 应用自动修复 | `python -m pylance mcp_s_pylanceInvokeRefactoring --file src/preprocessor/document_preprocessor.py --name source.fixAll.pylance` | 所有告警修复 | `git restore src/preprocessor/` |
| 4 | [4] | 质量门验证 | `python tools/quality_gate.py` | 所有门通过 code_health > 75 | 查看 `logs/stage2/` 日志 |
| 5 | [5] | 提交变更 | `git add -A && git commit -m "S2-1: 预处理器优化 - 代码健康度提升"` | 提交成功 | 无（如失败，回到分支重做） |

**预期指标变化**:
- 圈复杂度: 7.2 → 6.0
- 类型注解覆盖: 76% → 92%
- 代码健康度: 70.0 → 75.0 (+5)

---

### 第二行：S2-2 抽取器模块重构

| 步骤 | 命令编号 | 操作 | 命令 | 预期结果 | 失败恢复 |
|------|---------|------|------|--------|--------|
| 6 | [6] | 创建分支 | `git checkout -b stage2-s2_2-extractor-refactor` | 分支创建成功 | `git branch -D stage2-s2_2-extractor-refactor` |
| 7 | [7] | 应用自动修复 | `python -m pylance mcp_s_pylanceInvokeRefactoring --file src/extractors/advanced_entity_extractor.py --name source.fixAll.pylance` | 所有告警修复 | `git restore src/extractors/` |
| 8 | [8] | 清理未使用导入 | `python -m pylance mcp_s_pylanceInvokeRefactoring --file src/extractors/advanced_entity_extractor.py --name source.unusedImports` | 导入清理完成 | `git restore src/extractors/` |
| 9 | [9] | 质量门验证 | `python tools/quality_gate.py` | 所有门通过 code_health > 80 | 查看日志 |
| 10 | [10] | 提交变更 | `git add -A && git commit -m "S2-2: 抽取器重构 - 代码质量优化"` | 提交成功 | 无 |

**预期指标变化**:
- 最大方法长度: 32 lines → 18 lines
- 异常覆盖: 60% → 90%
- 代码健康度: 75.0 → 80.0 (+5)

---

### 第三行：S2-3 语义建模模块稳定化

| 步骤 | 命令编号 | 操作 | 命令 | 预期结果 | 失败恢复 |
|------|---------|------|------|--------|--------|
| 11 | [11] | 创建分支 | `git checkout -b stage2-s2_3-semantic-stable` | 分支创建成功 | `git branch -D stage2-s2_3-semantic-stable` |
| 12 | [12] | 添加类型注解 | `python -m pylance mcp_s_pylanceInvokeRefactoring --file src/semantic_modeling/semantic_graph_builder.py --name source.addTypeAnnotation` | 注解补充完成 | `git restore src/semantic_modeling/` |
| 13 | [13] | 应用自动修复 | `python -m pylance mcp_s_pylanceInvokeRefactoring --file src/semantic_modeling/semantic_graph_builder.py --name source.fixAll.pylance` | 所有告警修复 | `git restore src/semantic_modeling/` |
| 14 | [14] | 质量门验证 | `python tools/quality_gate.py` | 所有门通过 code_health > 80 | 查看日志 |
| 15 | [15] | 提交变更 | `git add -A && git commit -m "S2-3: 语义建模稳定化 - 边界条件加固"` | 提交成功 | 无 |

**预期指标变化**:
- 代码重复率: 12% → 6%
- 边界测试覆盖: 70% → 92%
- 代码健康度: 80.0 → 85.0 (+5)

---

### 第四行：S2-4 推理引擎优化

| 步骤 | 命令编号 | 操作 | 命令 | 预期结果 | 失败恢复 |
|------|---------|------|------|--------|--------|
| 16 | [16] | 创建分支 | `git checkout -b stage2-s2_4-reasoning-opt` | 分支创建成功 | `git branch -D stage2-s2_4-reasoning-opt` |
| 17 | [17] | 应用自动修复 | `python -m pylance mcp_s_pylanceInvokeRefactoring --file src/reasoning/reasoning_engine.py --name source.fixAll.pylance` | 所有告警修复 | `git restore src/reasoning/` |
| 18 | [18] | 运行测试套件 | `python -m pytest tests/unit/ -v --tb=short | grep -E "(PASS\|FAIL)"` | 所有测试通过 | 查看失败原因 |
| 19 | [19] | 质量门验证 | `python tools/quality_gate.py` | 所有门通过 code_health > 83 | 查看日志 |
| 20 | [20] | 提交变更 | `git add -A && git commit -m "S2-4: 推理引擎优化 - 幂等性验证"` | 提交成功 | 无 |

**预期指标变化**:
- 幂等性覆盖: 80% → 100%
- 状态转换合法性: 85% → 100%
- 代码健康度: 85.0 → 88.0 (+3)

---

### 第五行：S2-5 输出生成器强化

| 步骤 | 命令编号 | 操作 | 命令 | 预期结果 | 失败恢复 |
|------|---------|------|------|--------|--------|
| 21 | [21] | 创建分支 | `git checkout -b stage2-s2_5-output-strengthen` | 分支创建成功 | `git branch -D stage2-s2_5-output-strengthen` |
| 22 | [22] | 添加类型注解 | `python -m pylance mcp_s_pylanceInvokeRefactoring --file src/output/output_generator.py --name source.addTypeAnnotation` | 注解补充完成 | `git restore src/output/` |
| 23 | [23] | 应用自动修复 | `python -m pylance mcp_s_pylanceInvokeRefactoring --file src/output/output_generator.py --name source.fixAll.pylance` | 所有告警修复 | `git restore src/output/` |
| 24 | [24] | 质量门验证 | `python tools/quality_gate.py` | 所有门通过 code_health > 85 | 查看日志 |
| 25 | [25] | 提交变更 | `git add -A && git commit -m "S2-5: 输出生成器强化 - 契约验证完整化"` | 提交成功 | 无 |

**预期指标变化**:
- 契约验证覆盖: 78% → 100%
- 异常路径: 82% → 100%
- 代码健康度: 88.0 → 92.0 (+4)

---

### 第六行：S2-6 质量评估与合并

| 步骤 | 命令编号 | 操作 | 命令 | 预期结果 | 失败恢复 |
|------|---------|------|------|--------|--------|
| 26 | [26] | 验证分支状态 | `git branch \| grep stage2- \| wc -l` | 显示5个S2分支 | 无 |
| 27 | [27] | 全量品质门 | `python tools/quality_gate.py` | 所有门通过 | 查看详细报告 |
| 28 | [28] | 品质评估 | `python tools/quality_assessment.py --gates-report output/quality-gate.json` | overall_score > 96.0 | 查看维度得分 |
| 29 | [29] | 持续改进循环 | `python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json` | 生成建议和backlog | 无 |
| 30 | [30] | 存档指标 | `python tools/quality_improvement_archive.py` | 存档完成 | 无 |
| 31 | [31] | 反馈生成 | `python tools/quality_feedback.py` | 生成feedback报告 | 无 |
| 32 | [32] | 最终提交 | `git add -A && git commit -m "S2-6: Stage 2 完成 - 质量评分综合提升"` | 提交成功 | 无 |

**最终预期指标**:
- code_health: 70.0 → 85.0+ (+15.0)
- overall_score: 94.0 → 96.0+ (+2.0)
- grade: A → A+ (稳定)

---

## 执行顺序（逐条执行）

**命令序列编号 [1-32]** 按以下顺序逐一执行，每条完毕后再执行下一条：

```
[S2-1] → [1] [2] [3] [4] [5]
[S2-2] → [6] [7] [8] [9] [10]
[S2-3] → [11] [12] [13] [14] [15]
[S2-4] → [16] [17] [18] [19] [20]
[S2-5] → [21] [22] [23] [24] [25]
[S2-6] → [26] [27] [28] [29] [30] [31] [32]
```

---

## 异常处理规则

### 当某个 Sx 阶段失败时

1. **立即停止执行**后续阶段
2. **查看错误日志**：`logs/stage2/stage2_s2_x_*.log`
3. **识别问题类型**：
   - 代码告警未修复 → 手动编辑 + 重新运行 Pylance
   - 测试失败 → 查看单元测试报告 + 修复代码
   - Git 冲突 → 解决冲突 + 重新提交
4. **恢复步骤**：
   - `git restore .` 清理未提交更改
   - `git reset --soft HEAD~1` 撤销上一次提交（如需）
   - 修复问题后重新运行该阶段

### 关键检查点

- **[5], [10], [15], [20], [25]**: 每个 Sx 的最后检查点
- **[27]**: S2-6 的第一个关键检查点（全量品质门）
- **[28]**: 最关键检查点（overall_score 必须 > 96.0）

---

## 预期时间线

| 阶段 | 预期时间 | 累计 | 关键里程碑 |
|------|---------|------|----------|
| S2-1 | 15-20 min | 15-20 min | 预处理器优化 ✓ |
| S2-2 | 12-15 min | 27-35 min | 抽取器重构 ✓ |
| S2-3 | 12-15 min | 39-50 min | 语义稳定化 ✓ |
| S2-4 | 10-12 min | 49-62 min | 推理优化 ✓ |
| S2-5 | 12-15 min | 61-77 min | 输出强化 ✓ |
| S2-6 | 15-20 min | 76-97 min | **Stage 2 完成** ✓ |

**总计**: ~90 分钟（1.5 小时）

