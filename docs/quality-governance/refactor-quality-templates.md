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

Debt = alpha * warnings + beta * complexity_hotspots + gamma * flaky_tests

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

ROI = (delta_quality_score + delta_stability_score) / engineering_hours

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
