## 变更说明

- 背景：
- 目标：
- 范围：

## 重构前后复杂度检查项

### 目标函数与职责边界

- [ ] 本次重构函数数量已明确（N= ）
- [ ] 单一职责
- [ ] 输入/输出契约明确
- [ ] 对外接口兼容

### 控制流复杂度

- [ ] 嵌套层级下降或不回退
- [ ] 长链 if/elif 已规则化
- [ ] 使用早返回降低嵌套
- [ ] 重复分支已提取

### 风险与一致性

- [ ] 主路径行为一致
- [ ] 边界行为一致
- [ ] 异常路径一致
- [ ] 输出字段兼容

### 度量填写

- 复杂度告警：前 -> 后
- 高复杂函数告警：前 -> 后
- 质量门结果：通过/失败

## 必补单测项

- [ ] 主路径用例
- [ ] 边界用例（空输入/最小输入/缺字段）
- [ ] 异常用例（依赖失败）
- [ ] 新增辅助函数覆盖
- [ ] 规则命中与默认分支覆盖
- [ ] 至少 1 条集成烟测

## 回归命令执行记录

```bash
python -m unittest tests.unit.test_xxx tests.test_yyy
python tools/quality_gate.py --report output/quality-gate.json
python tools/quality_assessment.py --gates-report output/quality-gate.json --output output/quality-assessment.json
python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json --history output/quality-history.jsonl --output output/continuous-improvement.json
python tools/quality_improvement_archive.py --output output/quality-improvement-archive-latest.json
```

## 执行结果

- 单测结果：
- 质量门：
- 质量评分：
- 趋势状态：
- 档案生成：

## 风险与回滚

- 主要风险：
- 回滚策略：
