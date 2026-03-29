# 重构与质量保障标准模板

本文档统一沉淀以下三套模板，供重构类 PR 直接复用：

1. 重构前后复杂度检查项
2. 必补单测项
3. 回归命令标准化模板

## 1. 重构前后复杂度检查项

### 1.1 目标函数与职责边界

- [ ] 本次重构函数数量已明确（填写：N）
- [ ] 每个目标函数满足单一职责
- [ ] 每个目标函数输入/输出契约明确
- [ ] 对外接口（函数签名/返回结构）兼容

### 1.2 控制流复杂度

- [ ] 最大嵌套层级下降或保持不变
- [ ] 长链 if/elif 已替换为规则表或映射
- [ ] 使用早返回减少金字塔嵌套
- [ ] 重复分支逻辑已提取为复用函数

### 1.3 可维护性

- [ ] 主流程已编排化（流程函数 + 细节子函数）
- [ ] 重复代码减少（填写：前 -> 后）
- [ ] 复杂代码块补充必要注释（非啰嗦注释）
- [ ] 错误处理路径可读且一致

### 1.4 风险与行为一致性

- [ ] 主路径行为与重构前一致
- [ ] 边界输入行为不回退
- [ ] 异常路径行为不回退
- [ ] 序列化输出字段保持兼容

### 1.5 度量结果（PR 需填写）

- 复杂度告警数：前 -> 后
- 高复杂函数告警：前 -> 后
- 质量门结果：通过/失败
- 说明：

## 2. 必补单测项

### 2.1 功能正确性

- [ ] 主路径用例：合法输入 + 关键输出断言
- [ ] 边界用例：空输入/最小输入/缺字段输入
- [ ] 异常用例：依赖抛错时行为断言

### 2.2 分支与规则覆盖

- [ ] 新增辅助函数均有至少 1 个单测
- [ ] 规则表覆盖命中分支
- [ ] 规则表覆盖未命中默认分支
- [ ] 错误分支覆盖到可观测输出

### 2.3 回归与兼容

- [ ] 重构前关键行为快照断言（字段、状态、语义）
- [ ] 至少 1 条轻量集成烟测
- [ ] 无新增不稳定测试（flaky）

## 3. 回归命令标准化模板

按顺序执行并在 PR 说明中粘贴结果：

```bash
# 1) 定向单测（替换为本次相关测试）
python -m unittest tests.unit.test_xxx tests.test_yyy

# 2) 统一质量门
python tools/quality_gate.py --report output/quality-gate.json

# 3) 质量评估
python tools/quality_assessment.py --gates-report output/quality-gate.json --output output/quality-assessment.json

# 4) 持续改进循环
python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json --history output/quality-history.jsonl --output output/continuous-improvement.json

# 5) 质量改进档案
python tools/quality_improvement_archive.py --output output/quality-improvement-archive-latest.json
```

## 4. PR 结论填写模板

请在 PR 描述中附上：

```text
复杂度检查：通过/未通过
必补单测：通过/未通过（X passed, Y failed）
质量门：通过/失败
质量评分：XX.X（等级 X）
趋势状态：improving/stable/regressing
是否生成档案：是/否
风险说明：
```

## 5. 严谨性提升示例（正式规范）

本章节用于指导重构类需求从“可运行”提升到“可验证、可追溯、可复现”。

### 5.1 输入契约严谨化

- 规范要求：入口函数必须进行必填字段与类型校验。
- 建议做法：先校验再执行业务，失败时返回结构化错误对象。
- 验证标准：缺字段、类型错误场景有明确错误码或错误类型。

示例：

```python
def run_quality_assessment(report: dict) -> dict:
    required = ["results"]
    missing = [k for k in required if k not in report]
    if missing:
        return {"ok": False, "error": "missing_fields", "fields": missing}
    if not isinstance(report["results"], list):
        return {"ok": False, "error": "invalid_type", "field": "results"}
    return {"ok": True}
```

### 5.2 配置读取严谨化（容错 + 默认回退）

- 规范要求：配置解析异常不得直接阻断主流程。
- 建议做法：解析失败时回退默认值并记录来源。
- 验证标准：异常配置文件下流程可继续，且阈值可观测。

示例：

```python
def load_thresholds(path):
    try:
        data = parse_yaml(path)
    except Exception:
        return {"min_score": 85.0, "source": "default_fallback"}
    return {"min_score": float(data.get("min_score", 85.0)), "source": "config"}
```

### 5.3 规则判定严谨化（规则表 + 默认分支）

- 规范要求：复杂分类逻辑优先使用规则表，且必须保留默认分支。
- 建议做法：规则与逻辑分离，便于扩展和审查。
- 验证标准：命中规则与未命中规则均有单测覆盖。

示例：

```python
RULES = [
    (("security", "vulnerability"), "security_vulnerability"),
    (("timeout", "slow"), "performance_issue"),
]

def classify(msg: str) -> str:
    low = msg.lower()
    for keys, issue_type in RULES:
        if any(k in low for k in keys):
            return issue_type
    return "general_issue"
```

### 5.4 指标计算严谨化（边界保护）

- 规范要求：所有评分计算必须处理零分母、空输入、None 值。
- 建议做法：统一使用安全计算函数并做区间钳制。
- 验证标准：边界输入不抛异常，结果范围稳定在预期区间。

示例：

```python
def safe_ratio(num: float, den: float) -> float:
    if den <= 0:
        return 1.0
    value = num / den
    return max(0.0, min(1.0, value))
```

### 5.5 档案追溯严谨化（timeline + latest + dossier）

- 规范要求：每轮质量迭代必须沉淀可追溯档案。
- 建议做法：并行输出 JSONL 时间线、JSON 最新快照、Markdown 单次档案。
- 验证标准：机器可追踪、人工可复盘、历史可对比。

示例：

```python
entry = {"ts": now_iso(), "score": 96.5, "trend": "stable"}
append_jsonl("output/quality-history.jsonl", entry)
write_json("output/quality-latest.json", entry)
write_md("docs/quality-archive/entry-xxx.md", entry)
```

### 5.6 测试严谨化（最小必测集合）

- 规范要求：每个重构点至少补齐四类测试。

必测清单：

- [ ] 主路径正确性
- [ ] 边界输入（空输入/缺字段/类型错误）
- [ ] 异常路径（依赖抛错）
- [ ] 默认分支（规则未命中）

### 5.7 回归严谨化（固定顺序）

- 规范要求：回归验证顺序固定，避免遗漏。

执行顺序：

1. 定向单测
2. 统一质量门
3. 质量评估
4. 持续改进循环
5. 质量改进档案

### 5.8 结果表达严谨化（可审计）

- 规范要求：PR 结果描述必须量化、可复核。
- 禁止描述："优化了很多"、"明显更好" 等不可审计表述。

建议填写：

- 告警数：前 -> 后
- 高复杂函数数：前 -> 后
- 质量评分：前 -> 后
- 趋势状态：improving/stable/regressing
- 证据文件：报告与档案路径

## 6. 创新性提升示例（正式规范）

本章节用于指导质量治理从“结果检查”升级到“预测与决策驱动”。

### 6.1 从静态阈值到自适应阈值

- 创新目标：让阈值随历史表现动态调整，而非长期固定。
- 推荐机制：连续高分上调阈值，出现回归冻结阈值并触发专项整改。

落地命令：

```bash
python tools/quality_assessment.py --gates-report output/quality-gate.json --output output/quality-assessment.json
python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json --history output/quality-history.jsonl --output output/continuous-improvement.json
```

验收标准：

- [ ] 连续 3 次高分后阈值策略有调整记录
- [ ] 回归周期触发冻结策略或整改行动
- [ ] 阈值来源可追溯（配置或回退）

### 6.2 从“结果报告”到“行动编排”

- 创新目标：建议可执行、可关闭，而非仅文本建议。
- 推荐机制：将建议结构化为 P0/P1/P2 行动单并绑定目标指标。

落地命令：

```bash
python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json --history output/quality-history.jsonl --output output/continuous-improvement.json
```

验收标准：

- [ ] 行动清单含优先级和改进维度
- [ ] 下一周期目标字段完整
- [ ] 行动条目可被档案系统记录

### 6.3 引入质量债务指标

- 创新目标：识别“当前可过门禁但长期有风险”的隐性问题。
- 推荐机制：组合告警、复杂度热点、测试稳定性为统一债务分。

建议公式：

`Debt = alpha * warnings + beta * complexity_hotspots + gamma * flaky_tests`

落地命令：

```bash
python tools/quality_gate.py --report output/quality-gate.json
python tools/quality_assessment.py --gates-report output/quality-gate.json --output output/quality-assessment.json
```

验收标准：

- [ ] 债务分可从报告字段复算
- [ ] 债务分变化与告警变化同向
- [ ] 债务分进入改进行动优先级判定

### 6.4 增加改进 ROI 评估

- 创新目标：优先投入高收益改进项。
- 推荐机制：记录改进投入工时并对照质量增益计算 ROI。

建议公式：

`ROI = (delta_quality_score + delta_stability_score) / engineering_hours`

落地命令：

```bash
python tools/quality_improvement_archive.py --output output/quality-improvement-archive-latest.json
```

验收标准：

- [ ] 档案中有可用于 ROI 计算的前后评分数据
- [ ] 每轮改进有工时或投入说明
- [ ] 下轮计划优先选择高 ROI 行动

### 6.5 从单点评分到趋势预测

- 创新目标：从“事后复盘”升级为“提前预警”。
- 推荐机制：基于历史时间线生成短期预测区间与置信标记。

落地命令：

```bash
python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json --history output/quality-history.jsonl --output output/continuous-improvement.json
```

验收标准：

- [ ] 报告中至少包含 trend_status 与 score_delta
- [ ] 历史点数量持续增长且可追踪
- [ ] 出现连续回归时可触发专项整改建议

### 6.6 增加创新实验槽位

- 创新目标：在不破坏主干稳定性的前提下试验新规则。
- 推荐机制：实验规则先告警不阻断，稳定后再升级为正式 gate。

落地命令：

```bash
python tools/code_quality_checks.py
python tools/quality_gate.py --report output/quality-gate.json
```

验收标准：

- [ ] 实验规则不影响主流程通过条件
- [ ] 实验期内有独立记录与评估
- [ ] 达标后有明确晋升条件

### 6.7 引入证据链评分

- 创新目标：降低主观判断，提高评审一致性。
- 推荐机制：要求每次改进提交“测试结果 + 质量门 + 档案快照”。

落地命令：

```bash
python -m unittest tests.unit.test_xxx
python tools/quality_gate.py --report output/quality-gate.json
python tools/quality_improvement_archive.py --output output/quality-improvement-archive-latest.json
```

验收标准：

- [ ] 每次改进均附三类证据
- [ ] 证据路径在 PR 中可访问
- [ ] 证据缺失时 PR 不进入合并阶段

### 6.8 从工具驱动到机制驱动

- 创新目标：形成可复制、可扩展、可审计的治理节奏。
- 推荐机制：固定五段循环：检查、评估、改进、归档、复盘。

落地命令：

```bash
python tools/quality_gate.py --report output/quality-gate.json
python tools/quality_assessment.py --gates-report output/quality-gate.json --output output/quality-assessment.json
python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json --history output/quality-history.jsonl --output output/continuous-improvement.json
python tools/quality_improvement_archive.py --output output/quality-improvement-archive-latest.json
```

验收标准：

- [ ] 五段流程均有产物文件
- [ ] 每段输入输出关系明确
- [ ] 可从档案完整回放单次治理周期

## 7. D11 验证逻辑补充检查项

本章节用于 D11 类验证阶段重构，强调验证结果结构、失败路径和可复核证据。

### 7.1 验证覆盖率

- [ ] 验证用例覆盖率达到 90% 以上
- [ ] 验证逻辑的边界条件已测试
- [ ] 空输入与零结果场景不抛异常

### 7.2 验证性能

- [ ] 验证时间符合预期（填写：实际时间）
- [ ] 验证结果的置信度提升率已记录
- [ ] 验证阶段耗时字段可稳定输出

### 7.3 验证结果一致性

- [ ] 验证结果与预期一致
- [ ] 验证失败路径已记录并分析
- [ ] 返回结构字段在成功与失败路径上保持兼容

## 8. D12 优化逻辑补充检查项

本章节用于 D12 类优化阶段重构，强调优化动作生成、优先级排序与阈值驱动的一致性。

### 8.1 优化动作覆盖率

- [ ] 质量分低于阈值时可生成优化动作
- [ ] 置信度低于阈值时可生成优化动作
- [ ] 空分析结果返回稳定的空优化结构

### 8.2 优化决策稳定性

- [ ] 优化动作按优先级排序输出
- [ ] 最大优化动作数受配置约束
- [ ] 优化摘要包含当前分数与目标阈值

### 8.3 优化结果可复核性

- [ ] 每个优化动作包含时间戳与预期收益
- [ ] 优化摘要可区分 `optimization_required` 与 `no_action_needed`
- [ ] 优化阶段结果在迭代元数据中可追踪

## 9. D13 系统洞察补充检查项

本章节用于 D13 类系统级重构，强调系统洞察、学术洞察与推荐结果的结构一致性。

### 9.1 系统级结果完整性

- [ ] 系统级结果同时输出 `system_insights`、`academic_insights`、`recommendations`
- [ ] 系统级分析摘要包含模块数、失败模块数和总体状态
- [ ] 成功与失败模块均可被统一识别

### 9.2 学术洞察一致性

- [ ] 学术合规状态可转化为独立学术洞察
- [ ] 学术质量指标可生成可复核描述
- [ ] 学术质量低于阈值时会输出缺口洞察

### 9.3 系统建议可执行性

- [ ] 推荐结果保持列表结构，避免字典/列表漂移
- [ ] 失败模块会生成专项跟进建议
- [ ] 推荐数量受配置上限约束

## 10. D14 流程编排补充检查项

本章节用于 D14 类主流程重构，强调阶段编排标准化、失败路径可追踪性与结果契约统一。

### 10.1 阶段状态机一致性

- [ ] 主流程阶段通过统一执行辅助函数推进
- [ ] 每个阶段都记录开始、结束、耗时与状态
- [ ] 失败时可定位 `failed_phase` 与最后一个成功阶段

### 10.2 元数据可观测性

- [ ] 迭代元数据输出 `phase_history` 与 `phase_timings`
- [ ] 分析阶段输出独立 `analysis_summary`
- [ ] 成功与失败路径均输出最终状态字段

### 10.3 结果契约稳定性

- [ ] 质量评分字段兼容 `overall_quality` 与 `quality_score`
- [ ] 失败迭代可被持久化并进入摘要报告
- [ ] 新增编排字段不破坏既有对外结果结构

## 11. D15 导出契约补充检查项

本章节用于 D15 类结果归档重构，强调摘要、导出与 JSON 序列化契约的一致性。

### 11.1 JSON 可序列化性

- [ ] 导出结果不直接暴露不可序列化对象
- [ ] 枚举状态字段在导出结构中转为稳定字符串
- [ ] 导出文件可被 `json.load` 直接回读

### 11.2 摘要与导出对齐

- [ ] 摘要中的 `latest_results` 与导出结果结构一致
- [ ] 系统级报告输出失败迭代明细
- [ ] 导出载荷包含统一的 `report_metadata`

### 11.3 归档治理完整性

- [ ] 导出载荷包含契约版本与生成时间
- [ ] 导出结构保留配置、性能指标与失败明细
- [ ] D15 变更未破坏既有主流程与系统级测试

## 12. D16 模块级对齐补充检查项

本章节用于 D16 类模块级重构，强调模块迭代与循环级、系统级契约保持一致，并修正清理阶段的资源安全性。

### 12.1 模块结果契约一致性

- [ ] 模块级结果输出 `analysis_summary`
- [ ] 模块级 `recommendations` 保持列表结构
- [ ] 模块级质量评分兼容 `overall_quality` 与 `quality_score`

### 12.2 模块阶段可观测性

- [ ] 模块级迭代记录 `phase_history` 与 `phase_timings`
- [ ] 模块失败路径记录 `failed_phase`
- [ ] 模块报告输出失败迭代明细与 `report_metadata`

### 12.3 资源清理安全性

- [ ] 模块级与循环级 cleanup 仅清理自身状态
- [ ] 共享执行器不会在局部 cleanup 中被关闭
- [ ] D16 变更未破坏既有 cycle 回归测试

## 13. D17 测试驱动迭代补充检查项

本章节用于 D17 类测试驱动迭代重构，强调测试阶段轨迹、分析摘要与导出契约统一。

### 13.1 测试迭代契约一致性

- [ ] 测试驱动迭代输出 `analysis_summary`
- [ ] 失败测试数量、通过率与总体状态可稳定追踪
- [ ] 失败路径进入 `failed_iterations` 明细

### 13.2 测试阶段可观测性

- [ ] 测试驱动迭代记录 `phase_history` 与 `phase_timings`
- [ ] 失败阶段写入 `failed_phase`
- [ ] 导出报告包含统一 `report_metadata`

### 13.3 导出与资源安全

- [ ] 导出测试套件时不会直接暴露函数对象
- [ ] 导出文件可被 `json.load` 直接回读
- [ ] cleanup 会同时清理历史与失败记录

## 14. D18 修复阶段补充检查项

本章节用于 D18 类修复阶段重构，强调修复阶段编排、失败阶段追踪与 JSON 安全导出契约统一。

### 14.1 修复阶段契约一致性

- [ ] 修复阶段主流程输出 `analysis_summary`
- [ ] 修复行动、阶段历史、失败阶段均保持稳定列表结构
- [ ] 修复性能报告输出统一 `report_metadata`

### 14.2 修复阶段可观测性

- [ ] 修复阶段记录 `phase_history` 与 `phase_timings`
- [ ] 失败阶段写入 `failed_phase`
- [ ] 完成阶段记录 `completed_phases` 与 `final_status`

### 14.3 导出与指标安全

- [ ] 导出修复行动时不会直接暴露枚举对象
- [ ] 导出文件可被 `json.load` 直接回读
- [ ] 修复指标不会重复累计成功数与失败数

## 15. D19 研究流程补充检查项

本章节用于 D19 类 research pipeline 重构，强调研究阶段轨迹、失败循环治理、导出契约与共享资源安全统一。

### 15.1 研究流程契约一致性

- [ ] 研究循环状态输出 `analysis_summary`
- [ ] 研究循环导出包含稳定 `failed_cycles` 列表
- [ ] 流程摘要与导出结果输出统一 `report_metadata`

### 15.2 研究阶段可观测性

- [ ] 研究循环记录 `phase_history` 与 `phase_timings`
- [ ] 阶段异常写入 `failed_phase`
- [ ] 完成、暂停、恢复会同步刷新 `final_status`

### 15.3 资源与导出安全

- [ ] 流程 cleanup 仅清理自身状态，不关闭共享执行器
- [ ] 导出研究循环时不会暴露枚举对象
- [ ] 导出文件可被 `json.load` 直接回读

## 16. D20 理论框架补充检查项

本章节用于 D20 类 theoretical framework 重构，强调研究操作轨迹、失败操作沉淀、摘要契约与导出一致性统一。

### 16.1 理论框架契约一致性

- [ ] 理论框架摘要输出 `analysis_summary`
- [ ] 失败操作以稳定 `failed_operations` 列表输出
- [ ] 框架摘要与导出结果输出统一 `report_metadata`

### 16.2 研究操作可观测性

- [ ] 假设、实验、洞察、验证、知识图谱构建记录 `phase_history`
- [ ] 失败操作写入 `failed_phase`
- [ ] 成功操作刷新 `completed_phases` 与 `last_completed_phase`

### 16.3 导出与知识安全

- [ ] 假设、实验、洞察导出不会暴露枚举对象
- [ ] 导出文件可被 `json.load` 直接回读
- [ ] 知识图谱导出与研究摘要保持同一契约版本

## 17. D21 算法优化器补充检查项

本章节用于 D21 类 algorithm optimizer 重构，强调优化阶段轨迹、失败操作沉淀、摘要契约与导出一致性统一。

### 17.1 优化器契约一致性

- [ ] 优化器报告输出 `analysis_summary`
- [ ] 失败操作以稳定 `failed_operations` 列表输出
- [ ] benchmark 与导出结果输出统一 `report_metadata`

### 17.2 优化阶段可观测性

- [ ] `run_best`、`benchmark` 与算法执行记录 `phase_history`
- [ ] 失败操作写入 `failed_phase`
- [ ] 成功路径刷新 `completed_phases` 与 `last_completed_phase`

### 17.3 导出与画像安全

- [ ] 算法画像导出不会暴露不可序列化对象
- [ ] 导出文件可被 `json.load` 直接回读
- [ ] D21 变更未破坏既有 learning/optimization 回归测试

## 18. D22 系统架构补充检查项

本章节用于 D22 类 system architecture 重构，强调系统级阶段轨迹、失败操作沉淀、状态摘要契约与 JSON 安全导出统一。

### 18.1 系统架构契约一致性

- [ ] 系统状态输出 `analysis_summary`
- [ ] 失败操作以稳定 `failed_operations` 列表输出
- [ ] 系统摘要与导出结果输出统一 `report_metadata`

### 18.2 系统阶段可观测性

- [ ] 模块注册、初始化、激活、流水线执行记录 `phase_history`
- [ ] 阶段异常写入 `failed_phase`
- [ ] 成功路径刷新 `completed_phases` 与 `last_completed_phase`

### 18.3 导出与序列化安全

- [ ] 模块信息导出不会暴露枚举或 dataclass 原始对象
- [ ] 导出文件可被 `json.load` 直接回读
- [ ] D22 变更未破坏既有 architecture/cycle 回归测试

## 19. D23 自动化测试框架补充检查项

本章节用于 D23 类 automated tester 重构，强调测试编排轨迹、失败操作沉淀、测试摘要契约与共享执行器安全统一。

### 19.1 自动化测试契约一致性

- [ ] 测试报告输出 `analysis_summary`
- [ ] 失败操作以稳定 `failed_operations` 列表输出
- [ ] 测试性能报告与导出结果输出统一 `report_metadata`

### 19.2 测试编排可观测性

- [ ] 测试套件添加、套件执行、全集执行记录 `phase_history`
- [ ] 阶段异常写入 `failed_phase`
- [ ] 成功路径刷新 `completed_phases` 与 `last_completed_phase`

### 19.3 导出与资源安全

- [ ] 导出测试套件时不会直接暴露函数对象
- [ ] 导出文件可被 `json.load` 直接回读
- [ ] cleanup 仅清理实例状态，不关闭共享执行器

## 20. D24 集成测试框架补充检查项

本章节用于 D24 类 integration tester 重构，强调集成测试轨迹、失败操作沉淀、测试摘要契约与共享执行器安全统一。

### 20.1 集成测试契约一致性

- [ ] 集成测试报告输出 `analysis_summary`
- [ ] 失败操作以稳定 `failed_operations` 列表输出
- [ ] 性能报告与导出结果输出统一 `report_metadata`

### 20.2 集成编排可观测性

- [ ] 环境创建、测试注册、单测执行、全集执行记录 `phase_history`
- [ ] 阶段异常写入 `failed_phase`
- [ ] 成功路径刷新 `completed_phases` 与 `last_completed_phase`

### 20.3 导出与资源安全

- [ ] 导出测试历史时不会暴露枚举或 dataclass 原始对象
- [ ] 导出文件可被 `json.load` 直接回读
- [ ] cleanup 仅清理实例状态，不关闭共享执行器

## 21. D25 算法优化器刷新补充检查项

本章节用于 D25 类 algorithm optimizer 二次治理对齐，强调优化轨迹元数据、失败操作结构、导出版本刷新与 cleanup 一致性。

### 21.1 优化器契约一致性

- [ ] 优化器摘要输出 `analysis_summary` 与 `final_status`
- [ ] 失败操作以稳定 `failed_operations` 列表输出，字段使用 `operation`
- [ ] 优化报告与导出结果输出统一 `report_metadata`

### 21.2 优化阶段可观测性

- [ ] `run_best`、`benchmark`、`invoke_algorithm`、导出记录 `phase_history`
- [ ] 阶段异常写入 `failed_phase`
- [ ] 成功路径刷新 `completed_phases` 与 `last_completed_phase`

### 21.3 导出与清理安全

- [ ] 优化器导出不会暴露不可序列化对象
- [ ] 导出文件可被 `json.load` 直接回读
- [ ] cleanup 后运行态元数据与画像统计重置为稳定空状态

## 22. D26 研究流程二次治理补充检查项

本章节用于 D26 类 research pipeline 二次治理对齐，强调 pipeline 级失败操作、cycle 级状态摘要、导出版本刷新与 cleanup 重置一致性。

### 22.1 研究流程契约一致性

- [ ] pipeline 摘要输出 `analysis_summary` 与 `final_status`
- [ ] cycle 摘要输出稳定状态语义，并保留 `final_status`
- [ ] 导出结果与流程摘要输出统一 `report_metadata`

### 22.2 流程与阶段可观测性

- [ ] 创建、启动、完成、暂停、恢复、导出记录 pipeline 级 `phase_history`
- [ ] 单个研究阶段异常写入 cycle 级 `failed_phase`
- [ ] 失败操作以稳定 `failed_operations` 列表输出，字段使用 `operation`

### 22.3 导出与清理安全

- [ ] 导出不会暴露枚举、dataclass 或 callable 原始对象
- [ ] 导出文件可被 `json.load` 直接回读
- [ ] cleanup 后实例状态重置，但共享执行器保持可用
