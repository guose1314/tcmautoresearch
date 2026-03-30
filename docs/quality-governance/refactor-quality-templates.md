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

## 89. D89 Issue Body 单对象可逆恢复与 Uncategorized Residual-Risk Recovery

- [ ] quality_feedback 的 issue draft 正文已由单个 issue_body 对象驱动，至少覆盖 summary、inventory_trend、action_items、acceptance_checks、artifact_references 五个区块
- [ ] issue index items、feedback 导出 issue_drafts、feedback report_metadata、issue index report_metadata 已同步暴露 issue_body / issue_bodies 稳定字段
- [ ] issue draft Markdown 不再依赖分散拼接恢复正文，而是从 issue_body 单对象渲染
- [ ] 单测与 replay harness 优先校验 issue_body 对象及其正文反向恢复，而不是继续扩散更多平铺派生列表断言
- [ ] 已新增 uncategorized_root_script residual-risk recovery 样本，语义为 inventory_trend = improving 但当前 uncategorized_root_script 仍未清零
- [ ] 上述 residual-risk 样本已覆盖 feedback 模块级单测、end-to-end、quality_gate replay harness，并验证 feedback loud / runner quiet 分流不变

## 90. D90 Issue Body 反向投影收敛与 Mixed Residual-Risk Priority

- [ ] quality_feedback 的 issue index / feedback report_metadata / 导出 issue_drafts 中平铺 issue 字段已改为从 issue_body 单一事实源反向投影，而不是独立维护第二套正文语义
- [ ] issue_body 已稳定承载 inventory_context，即使非 regressing 样本不渲染 Inventory Trend 区块，也能为兼容平铺字段提供统一来源
- [ ] mixed residual-risk 语义已明确：当 improving 但 missing_contract 与 uncategorized_root_script 同时残留时，quality-governance draft 同时保留两条 action item，且顺序为缺合同优先、未归类观测次之
- [ ] mixed residual-risk 样本已覆盖 feedback 模块级单测、end-to-end、quality_gate replay harness，并验证 feedback loud / runner quiet 分流与 issue_body 正文条件渲染一致

## 91. D91 Public Issue Contract Shrink

- [ ] quality_feedback 对外输出的 issue items 与导出 issue_drafts 已只保留身份字段、路径字段与 issue_body，不再暴露可由 issue_body 反向恢复的平铺语义字段
- [ ] feedback report_metadata 与 issue index report_metadata 已删除 issue quality/trend/inventory/action/acceptance 派生列表，仅保留 issue_body / issue_bodies 作为正文语义载体
- [ ] quality_feedback 合同版本已提升到 d69.v1，以标识公开 issue 契约完成收缩
- [ ] 单测与 replay harness 已改为显式断言被移除的平铺字段不存在，同时继续校验 issue_body 与 Markdown 正文可逆一致

## 92. D92 Internal Projection Cleanup And Output Symmetry

- [ ] quality_feedback 已删除内部 `_project_issue_item` 兼容投影层，issue 身份与路径元数据统一直接从 `issue_body.artifact_references` 汇总
- [ ] `build_issue_drafts` 的内部模型已不再携带 `quality_score / trend_status / inventory_* / action_items / acceptance_checks / body` 等重复平铺字段，只保留写盘所需身份字段、`output_file` 与 `issue_body`
- [ ] 对外导出的 `issue_drafts[*]` 已移除 `output_file`，避免把内部写盘文件名继续泄漏为公开合同字段
- [ ] quality_feedback 合同版本已提升到 d70.v1，以标识该次公开字段收缩与内部兼容层清理

## 93. D93 Reference Metadata Shrink

- [ ] feedback report_metadata 已删除 `issue_draft_owners / titles / files / templates / labels / index_positions` 影子列表，仅保留 `issue_draft_bodies`
- [ ] issue index report_metadata 已删除 `issue_files / owners / titles / templates / labels / index_positions` 影子列表，仅保留 `issue_bodies`
- [ ] feedback Markdown 中的 issue draft 文件清单已改为从 `issue_draft_bodies[*].artifact_references.issue_draft_file` 反向恢复，不再依赖冗余元数据列表
- [ ] quality_feedback 合同版本已提升到 d71.v1，以标识 issue 引用元数据的进一步收缩

## 94. D94 Public Issue Item Final Shrink

- [ ] 对外导出的 `issue_drafts[*]` 与 `issue_index_payload.items[*]` 已删除顶层 `owner / title / template / labels / file / index_position` 兼容字段，仅保留 `issue_body`
- [ ] 外部消费者统一通过 `issue_body.summary` 与 `issue_body.artifact_references` 读取 issue 身份、路径与排序信息，不再依赖 item 顶层平铺字段
- [ ] export 阶段已不再需要按身份二次拼装公开 issue_drafts，而是直接从 `issue_index_payload.items[*].issue_body` 生成最终公开列表
- [ ] quality_feedback 合同版本已提升到 d72.v1，以标识公开 issue item 完成最终收缩

## 95. D95 Issue Body Metadata Elimination

- [ ] feedback report_metadata 已删除最后一层 `issue_draft_bodies` 影子数组，不再复制公开 `issue_drafts[*].issue_body`
- [ ] issue index report_metadata 已删除最后一层 `issue_bodies` 影子数组，不再复制公开 `items[*].issue_body`
- [ ] feedback Markdown 中的 issue draft 文件清单已改为从公开 `issue_drafts[*].issue_body.artifact_references.issue_draft_file` 反向恢复，不再依赖任何 issue body 元数据镜像
- [ ] quality_feedback 合同版本已提升到 d73.v1，以标识 issue body 批量影子数组已被完全移除

## 25. D29 迭代循环二次治理补充检查项

- [ ] cycle 级 phase_history、phase_timings、completed_phases 已落地，且不覆盖单次 iteration 元数据
- [ ] failed_operations 使用稳定字段 operation、error、timestamp、duration_seconds
- [ ] analysis_summary 在 iteration 完成后回填 final_status、last_completed_phase、failed_operation_count
- [ ] report_metadata.contract_version 升级为 d29.v1，且包含 final_status / failed_operation_count
- [ ] export_results 输出 failed_operations、metadata，并保证 JSON 安全序列化
- [ ] cleanup 仅重置运行态数据，不关闭共享 executor

## 26. D30 修复阶段二次治理补充检查项

- [ ] fixing_stage 使用 d30.v1 合同，并统一从 governance_config 读取阈值与导出版本
- [ ] stage 级 failed_operations 使用 operation、error、timestamp、duration_seconds 稳定结构
- [ ] analysis_summary 在 run_fixing_stage 完成后回填 final_status、failed_phase、failed_operation_count
- [ ] get_repair_performance_report 同时输出 analysis_summary、metadata、failed_operations
- [ ] export_repair_data 输出 failed_operations、metadata，并保证 RepairAction/FixingStageResult JSON 安全序列化
- [ ] cleanup 重置 repair_history、failed_stages、failed_operations、performance_metrics，并将 final_status 标记为 cleaned

## 27. D31 模块迭代二次治理补充检查项

- [ ] module_iteration 使用 d31.v1 合同，并统一从 governance_config 读取最小稳定质量阈值与导出版本
- [ ] module 级 failed_operations 使用 operation、error、timestamp、duration_seconds 稳定字段
- [ ] analysis_summary 在 execute_module_iteration 完成后回填 final_status、failed_phase、failed_operation_count
- [ ] get_module_performance_report 输出 analysis_summary、metadata、failed_operations，避免只有 iteration_history 明细
- [ ] export_module_data 输出 failed_operations、metadata，并保证 ModuleIterationResult 与知识图谱结构 JSON 安全序列化
- [ ] cleanup 重置 failed_iterations、failed_operations、performance_metrics，并将 final_status 标记为 cleaned

## 28. D32 系统级迭代三次治理补充检查项

- [ ] system_iteration 使用 d32.v1 合同，消除与 d29-d31 子模块的版本倒挂
- [ ] 每次 execute_system_iteration 开始前重置 system_metadata，避免多轮运行状态串味
- [ ] analysis_summary 通过统一同步函数回填 final_status、failed_phase、failed_operation_count、last_completed_phase
- [ ] report_metadata 输出 final_status，并与 get_system_performance_report 和 export_system_data 保持一致
- [ ] export_system_data 顶层输出 metadata，便于机器侧直接消费系统运行态
- [ ] cleanup 后 get_system_performance_report 仍返回空态消息，不残留上一轮系统状态

## 29. D33 测试驱动迭代二次治理补充检查项

- [ ] test_driven_iteration 使用 d33.v1 合同，并统一从 governance_config 读取稳定通过率阈值与导出版本
- [ ] manager 级 failed_operations 使用 operation、error、timestamp、duration_seconds 稳定字段
- [ ] analysis_summary 在 run_test_driven_iteration 成功/失败后统一回填 final_status、failed_phase、failed_operation_count
- [ ] get_test_performance_report 输出 analysis_summary、metadata、failed_operations，而不只保留 iteration_history 明细
- [ ] export_test_data 输出 failed_operations、metadata，并保证 TestResult/TestDrivenIteration/test_suite 的 JSON 安全序列化
- [ ] cleanup 重置 test_suites、failed_iterations、failed_operations、performance_metrics，并将 final_status 标记为 cleaned

## 30. D34 系统架构二次治理补充检查项

- [ ] system_architecture 使用 d34.v1 合同，并在 report_metadata 中输出 result_schema 与 final_status
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段
- [ ] get_system_status 与 get_architecture_summary 复用统一 runtime metadata 结构，避免多处拼装漂移
- [ ] export_system_info 顶层输出 metadata，便于机器侧直接消费架构运行态
- [ ] cleanup 将系统状态与 final_status 同步为 cleaned，而不是残留 terminated 语义
- [ ] cleanup 后状态查询不残留历史 failed_operations 或旧 phase 数据

## 31. D35 自动化测试框架二次治理补充检查项

- [ ] automated_tester 使用 d35.v1 合同，并在 report_metadata 中输出 result_schema 与 final_status
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段
- [ ] get_test_performance_report 与 export_test_results 复用统一 runtime metadata，避免重复拼装
- [ ] analysis_summary 输出 last_completed_phase，便于测试编排轨迹复盘
- [ ] cleanup 保留共享执行器可用，同时将 final_status 标记为 cleaned
- [ ] 导出结果继续保持函数对象 JSON 安全序列化，且顶层 metadata 可直接被机器消费

## 32. D36 集成测试框架二次治理补充检查项

- [ ] integration_tester 使用 d36.v1 合同，并在 report_metadata 中输出 result_schema 与 final_status
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段
- [ ] get_integration_performance_report 复用统一 runtime metadata，并输出 failed_operations 便于追踪失败轨迹
- [ ] analysis_summary 输出 last_completed_phase，便于集成测试编排复盘
- [ ] cleanup 保留共享执行器可用，同时将 final_status 标记为 cleaned
- [ ] 导出结果继续保持 dataclass/enum 的 JSON 安全序列化，不残留旧 terminated 语义

## 33. D37 理论框架二次治理补充检查项

- [ ] theoretical_framework 使用 d37.v1 合同，并在 report_metadata 中输出 final_status
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段
- [ ] get_research_summary 与 export_research_data 输出统一 runtime metadata，避免 framework_metadata 结构漂移
- [ ] analysis_summary 持续输出 last_completed_phase，便于理论研究编排复盘
- [ ] export_research_data 顶层输出 metadata，便于机器侧直接消费理论框架运行态
- [ ] cleanup 后 final_status 保持 cleaned，且摘要继续呈现 idle 空闲态

## 34. D38 算法优化器二次治理补充检查项

- [ ] algorithm_optimizer 使用 d38.v1 合同，并在 report_metadata 中输出 final_status
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段
- [ ] get_optimization_summary 复用统一 runtime metadata，避免直接暴露内部 _metadata 可变结构
- [ ] analysis_summary 持续输出 last_completed_phase，便于算法选择轨迹复盘
- [ ] cleanup 后 final_status 使用 cleaned 语义，不残留 terminated
- [ ] 导出结果继续保持算法摘要与 profiles 的 JSON 安全结构，并保留 report_metadata

## 35. D39 研究流程管理二次治理补充检查项

- [ ] research_pipeline 使用 d39.v1 合同，并在 report_metadata 中输出 final_status
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段
- [ ] get_pipeline_summary 复用统一 runtime metadata，避免直接暴露内部 _metadata 可变结构
- [ ] export_pipeline_data 顶层输出 failed_operations 与 metadata，便于机器侧直接消费流程运行态
- [ ] 失败循环路径保留 details，便于追溯 cycle_id 与 cycle_name
- [ ] cleanup 后 final_status 保持 cleaned，且摘要继续呈现 idle 空闲态

## 36. D40 迭代循环三次治理补充检查项

- [ ] iteration_cycle 使用 d40.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段
- [ ] get_cycle_summary 与 export_results 复用统一 runtime metadata builder，避免直接暴露 cycle_metadata 可变结构
- [ ] phase 失败路径保留 iteration_id / cycle_number / status 等 details，便于回溯失败轨迹
- [ ] export_results 顶层输出 metadata 与 failed_operations，继续保持 JSON 安全序列化
- [ ] cleanup 后 final_status 保持 cleaned，且共享 executor 继续可用

## 37. D41 修复阶段三次治理补充检查项

- [ ] fixing_stage 使用 d41.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段
- [ ] get_repair_performance_report 与 export_repair_data 复用统一 runtime metadata builder，避免直接暴露 stage_metadata 可变结构
- [ ] phase 失败路径保留 stage_id / iteration_id / status 等 details，便于回溯修复失败轨迹
- [ ] run_fixing_stage 外层阶段元数据需完整保留，不能在启动后被重置丢失
- [ ] cleanup 后 final_status 保持 cleaned，且导出结果继续保持 JSON 安全序列化

## 38. D42 系统级迭代三次治理补充检查项

- [ ] system_iteration 使用 d42.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段
- [ ] get_system_performance_report 与 export_system_data 复用统一 runtime metadata builder，避免直接暴露 system_metadata 可变结构
- [ ] phase 失败路径保留 iteration_id / cycle_number / status 等 details，便于回溯系统级失败轨迹
- [ ] execute_system_iteration 外层失败也保留 failed_phase details，便于区分阶段失败与总控失败
- [ ] cleanup 后 final_status 保持 cleaned，且导出结果继续保持 JSON 安全序列化

## 39. D43 模块级迭代三次治理补充检查项

- [ ] module_iteration 使用 d43.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段
- [ ] get_module_performance_report 与 export_module_data 复用统一 runtime metadata builder，避免直接暴露 module_metadata 可变结构
- [ ] phase 失败路径保留 module_name / iteration_id / cycle_number / status 等 details，便于回溯模块失败轨迹
- [ ] execute_module_iteration 外层失败也保留 failed_phase details，便于区分阶段失败与总控失败
- [ ] cleanup 后 final_status 保持 cleaned，且导出结果继续保持 JSON 安全序列化

## 40. D44 研究流程管理三次治理补充检查项

- [ ] research_pipeline 使用 d44.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段
- [ ] get_pipeline_summary 与 export_pipeline_data 复用统一 runtime metadata builder，避免直接暴露内部 _metadata 可变结构
- [ ] 阶段失败路径同时写入 cycle.metadata.failed_operations 与 pipeline.failed_operations，便于区分循环侧与流程侧回溯
- [ ] 失败循环路径保留 cycle_id / cycle_name / status / failed_phase 等 details，便于追溯科研闭环失败轨迹
- [ ] cleanup 后 final_status 保持 cleaned，且导出结果继续呈现 JSON 安全结构

## 41. D45 系统架构三次治理补充检查项

- [ ] system_architecture 使用 d45.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase
- [ ] execute_pipeline 返回值与 get_system_status/export_system_info 复用统一 metadata/report_metadata builder，避免阶段完成前拼装造成漂移
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段，并保留 module_id / module_name 等细节
- [ ] export_system_info 导出文件在成功路径下反映 export_system_info 已完成后的 runtime metadata
- [ ] architecture_summary、system_status、导出 payload 保持 JSON 安全序列化且字段口径一致
- [ ] cleanup 后 final_status 保持 cleaned，不回退为 initialized 或历史流水线状态

## 42. D46 模块基类三次治理补充检查项

- [ ] module_base 使用 d46.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase
- [ ] initialize / execute / async_execute / export_module_data 共享统一 runtime metadata builder，避免 report/export 口径漂移
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段，并保留 module_name / context_keys 等执行细节
- [ ] get_performance_report 在有无执行历史两种场景下都输出 analysis_summary、metadata、report_metadata，便于机器侧稳定消费
- [ ] export_module_data 顶层继续输出 failed_operations 与 metadata，并在成功路径反映 export_module_data 已完成后的 runtime metadata
- [ ] cleanup 后 final_status 保持 cleaned，且不关闭共享全局 executor

## 43. D47 模块接口三次治理补充检查项

- [ ] module_interface 使用 d47.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase
- [ ] initialize / execute / cleanup / export_interface_data 共享统一 runtime metadata builder，避免静态契约层与运行态档案口径分叉
- [ ] execute 返回的 ModuleOutput.metadata 持续附带 failed_operations、runtime_metadata、report_metadata，便于调用方直接消费
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段，并保留 module_id / context_id / module_name 等上下文细节
- [ ] get_execution_report、get_module_info、get_interface_compatibility、validate_module_compliance 统一输出 metadata / report_metadata，保持 JSON 安全结构
- [ ] cleanup 后 final_status 保持 cleaned，同时不破坏既有 ModuleStatus.TERMINATED 兼容语义

## 44. D48 接口一致性测试框架三次治理补充检查项

- [ ] interface_consistency_test 使用 d48.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase
- [ ] validate_module_interfaces、get_compliance_report、export_test_results 共享统一 runtime metadata builder，避免治理消费端自身档案口径漂移
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段，并保留 module_count / output_path 等上下文细节
- [ ] validate_module_interfaces 产出结果补齐 metadata / report_metadata / failed_operations，便于上游质量门直接消费
- [ ] export_test_results 顶层输出 failed_operations 与 metadata，并在成功路径反映 export_test_results 已完成后的 runtime metadata
- [ ] cleanup 后 final_status 保持 cleaned，且 get_compliance_report/test_summary 继续返回空态可消费结构

## 45. D49 质量评估器三次治理补充检查项

- [ ] quality_assessment 使用 d49.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase / result_schema
- [ ] assess_from_gate_results 在不破坏 passed / overall_score / grade 兼容消费面的前提下，补齐 analysis_summary、failed_operations、metadata、report_metadata
- [ ] export_assessment_report 在写出 JSON 之前完成 export_assessment_report 阶段落账，确保落盘档案中的 last_completed_phase 指向导出阶段
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段，并保留 gate_count / config_path / output_path 等上下文细节
- [ ] quality_gate 下游仍只依赖既有 passed / overall_score / grade / failed_dimensions 语义，不因治理档案字段扩充而回归

### D48-D49 消费链合同衔接简表

| 阶段 | 模块 | 主要职责 | 关键产出入口 | 统一合同字段 | 下游消费方式 |
| --- | --- | --- | --- | --- | --- |
| D48 | `tests/test_interface_consistency.py` | 测试侧治理消费端，负责接口一致性验证与测试档案输出 | `validate_module_interfaces` / `get_compliance_report` / `export_test_results` | `metadata`、`report_metadata`、`analysis_summary`、`failed_operations`、`phase_history`、`final_status`、`last_completed_phase` | 上游质量门或人工复盘可直接读取统一档案，不再分别拼接 `test_results` 与 `performance_metrics` |
| D49 | `tools/quality_assessment.py` | 质量门下游评估器，将 gate 结果转换为 `overall_score`、`grade` 与治理档案 | `assess_from_gate_results` / `export_assessment_report` | `metadata`、`report_metadata`、`analysis_summary`、`failed_operations`、`derived_metrics`、`final_status`、`last_completed_phase` | `quality_gate` 继续只消费 `passed`、`overall_score`、`grade`、`failed_dimensions`，完整 JSON 留给持续改进链路 |

### D48-D49 衔接要点

| 衔接维度 | D48 口径 | D49 口径 | 当前统一要求 |
| --- | --- | --- | --- |
| 运行态轨迹 | `phase_history`、`phase_timings` | `phase_history`、`phase_timings` | 两端都必须稳定给出 `final_status` 与 `last_completed_phase` |
| 失败档案 | `failed_operations` | `failed_operations` | 字段统一为 `operation`、`error`、`details`、`timestamp`、`duration_seconds` |
| 报告元数据 | `report_metadata` | `report_metadata` | 都应包含 `contract_version`、`generated_at`、`result_schema`、`failed_operation_count` |
| 导出完成态 | 导出后 `last_completed_phase = export_test_results` | 导出后 `last_completed_phase = export_assessment_report` | 元数据必须在写盘前完成落账，避免档案状态早于文件状态 |
| 空态/复位语义 | `cleanup -> cleaned` | 函数式评估器无长期驻留 cleanup，但需显式保留 `completed/failed` 终态 | 消费端必须能从档案直接判断终态，而不是依赖隐式约定 |

### 后续推进约束

- [ ] 下一跳消费端模块优先复用 `metadata` / `report_metadata` / `failed_operations` 三类稳定字段，不再引入新的并行命名
- [ ] `result_schema` 保持“一模块一名称”，便于持续改进链路按 schema 做路由或聚合
- [ ] 任何导出型消费端都必须保证落盘后的 `last_completed_phase` 指向真实导出阶段

## 46. D50 持续改进环三次治理补充检查项

- [ ] continuous_improvement 使用 d50.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase / result_schema
- [ ] build_cycle_report 在不破坏 current_snapshot / trend / action_backlog / next_cycle_targets 兼容消费面的前提下，补齐 analysis_summary、failed_operations、metadata、report_metadata
- [ ] export_cycle_report 统一负责 history 追加与 report 写盘，并在写盘前完成 export_continuous_improvement_report 阶段落账
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段，并保留 history_length / history_path / output_path 等上下文细节
- [ ] quality_gate 下游仍只依赖既有 history_points / score_delta / trend_status / backlog_count 语义，不因治理档案字段扩充而回归

## 47. D51 质量改进档案三次治理补充检查项

- [ ] quality_improvement_archive 使用 d51.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase / result_schema
- [ ] build_archive_entry 在不破坏 overall_success / quality_score / quality_grade / trend_status / next_cycle_targets 兼容消费面的前提下，补齐 analysis_summary、failed_operations、metadata、report_metadata
- [ ] write_archive 在写入 JSONL、Markdown、latest JSON 之前完成 export_quality_improvement_archive 阶段落账，确保 latest 档案中的 last_completed_phase 指向导出阶段
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段，并保留 gate_result_count / history_path / latest_output / dossier_path 等上下文细节
- [ ] quality_gate 下游仍只依赖既有 archive_entry_written / quality_score / trend_status 语义，不因治理档案字段扩充而回归

## 48. D52 质量反馈器三次治理补充检查项

- [ ] quality_feedback 使用 d52.v1 合同，并在 report_metadata 中持续输出 final_status / last_completed_phase / result_schema
- [ ] build_feedback_report 在不破坏 feedback_level / headline / priority_actions / owner_notifications / issue_drafts 兼容消费面的前提下，补齐 analysis_summary、failed_operations、metadata、report_metadata
- [ ] export_feedback_report 统一负责 JSON、Markdown、issue draft 与 issue index 写盘，并在写盘前完成 export_quality_feedback_report 阶段落账
- [ ] failed_operations 使用 operation、error、details、timestamp、duration_seconds 稳定字段，并保留 output_path / markdown_path / issue_dir / issue_index 等上下文细节
- [ ] quality_gate 下游仍只依赖既有 feedback_level / priority_action_count / owner_count / owner_todo_count / issue_draft_count 语义，不因治理档案字段扩充而回归

## 49. D53 D49-D52 下游消费链文档化衔接表

- [ ] 用一张链路表串起 quality_assessment、continuous_improvement、quality_improvement_archive、quality_feedback 四段消费链，明确每段的输入、核心产出、导出入口与下游消费者
- [ ] 明确各阶段统一合同的稳定字段：metadata、report_metadata、analysis_summary、failed_operations、final_status、last_completed_phase
- [ ] 明确各阶段在 quality_gate 中保留兼容消费的最小字段集合，避免后续治理日误改既有门禁指标语义
- [ ] 明确导出型模块的共同约束：先完成导出阶段落账，再写盘，确保档案中的 last_completed_phase 反映真实最终阶段

### D49-D52 下游消费链总表

| 阶段 | 模块 | 上游输入 | 核心产出 | 导出入口 | quality_gate 兼容消费字段 | 后续消费者 |
| --- | --- | --- | --- | --- | --- | --- |
| D49 | `tools/quality_assessment.py` | `quality-gate.json` 中的 gate 结果 | `overall_score`、`grade`、`failed_dimensions`、治理档案 | `export_assessment_report` | `passed`、`overall_score`、`grade`、`failed_dimensions` | D50 持续改进环、人工质量复盘 |
| D50 | `tools/continuous_improvement_loop.py` | `quality-assessment.json` + `quality-history.jsonl` | `current_snapshot`、`trend`、`action_backlog`、`next_cycle_targets`、治理档案 | `export_cycle_report` | `history_points`、`score_delta`、`trend_status`、`backlog_count` | D51 质量改进档案、人工改进规划 |
| D51 | `tools/quality_improvement_archive.py` | gate 报告 + assessment 报告 + improvement 报告 | JSONL 时间线、Markdown dossier、latest JSON、治理档案 | `write_archive` | `archive_entry_written`、`quality_score`、`trend_status` | D52 质量反馈器、历史追溯与归档检索 |
| D52 | `tools/quality_feedback.py` | assessment 报告 + improvement 报告 + archive latest | feedback JSON、Markdown、owner notifications、issue drafts、治理档案 | `export_feedback_report` | `feedback_level`、`priority_action_count`、`owner_count`、`owner_todo_count`、`issue_draft_count` | 人工执行、责任分发、后续治理日 |

### D49-D52 统一合同字段对照

| 字段 | D49 | D50 | D51 | D52 | 统一要求 |
| --- | --- | --- | --- | --- | --- |
| `metadata` | 评估运行态 | 改进环运行态 | 档案运行态 | 反馈运行态 | 必须包含 `phase_history`、`phase_timings`、`completed_phases`、`failed_phase`、`final_status`、`last_completed_phase` |
| `report_metadata` | 评估报告元数据 | 改进报告元数据 | 档案报告元数据 | 反馈报告元数据 | 必须包含 `contract_version`、`generated_at`、`result_schema`、`failed_operation_count` |
| `analysis_summary` | 评估稳定性摘要 | 改进趋势摘要 | 档案健康摘要 | 反馈执行摘要 | 面向人和自动化链路的高层摘要，不替代原始细节字段 |
| `failed_operations` | 评估失败归档 | 改进失败归档 | 档案失败归档 | 反馈失败归档 | 稳定字段统一为 `operation`、`error`、`details`、`timestamp`、`duration_seconds` |
| `last_completed_phase` | `export_assessment_report` | `export_continuous_improvement_report` | `export_quality_improvement_archive` | `export_quality_feedback_report` | 必须在真实写盘前完成阶段落账，禁止提前生成最终 metadata |

### D49-D52 延续约束

- [ ] 新的治理消费端优先复用现有四段链路的稳定字段和导出阶段命名，不再引入新的并行合同术语
- [ ] `result_schema` 继续保持一模块一名称，便于归档检索、自动路由和跨阶段聚合
- [ ] quality_gate 只读取兼容消费字段，扩展治理档案时不得顺手改变门禁 metrics 的公开语义
- [ ] 若后续模块需要写多份文件，统一通过单个导出函数完成“阶段落账 + 多目标写盘”，避免 JSON、Markdown、索引文件之间状态不一致

### D48-D53 阶段性摘要

| 阶段 | 目标 | 已完成结果 | 保持兼容的消费面 |
| --- | --- | --- | --- |
| D48 | 将接口一致性测试框架升级为治理消费端 | `tests/test_interface_consistency.py` 已补齐 timeline / report / export 档案口径，导出后 `last_completed_phase` 指向 `export_test_results` | 既有 `compliance_report`、`academic_analysis`、`recommendations` 仍可原样消费 |
| D49 | 将质量评估器升级为统一档案合同 | `tools/quality_assessment.py` 已补齐 `metadata`、`report_metadata`、`analysis_summary`、`failed_operations`，并新增 `export_assessment_report` | quality_gate 仍只消费 `passed`、`overall_score`、`grade`、`failed_dimensions` |
| D50 | 将持续改进环升级为统一档案合同 | `tools/continuous_improvement_loop.py` 已补齐治理元数据，并通过 `export_cycle_report` 统一 history 追加与报告写盘 | quality_gate 仍只消费 `history_points`、`score_delta`、`trend_status`、`backlog_count` |
| D51 | 将质量改进档案升级为统一档案合同 | `tools/quality_improvement_archive.py` 已补齐治理元数据，并在 JSONL / Markdown / latest JSON 三类输出前完成导出阶段落账 | quality_gate 仍只消费 `archive_entry_written`、`quality_score`、`trend_status` |
| D52 | 将质量反馈器升级为统一档案合同 | `tools/quality_feedback.py` 已补齐治理元数据，并通过 `export_feedback_report` 统一 JSON / Markdown / issue drafts / issue index 写盘 | quality_gate 仍只消费 `feedback_level`、`priority_action_count`、`owner_count`、`owner_todo_count`、`issue_draft_count` |
| D53 | 将 D49-D52 下游消费链固化为文档资产 | 当前文档已具备链路总表、统一字段对照、延续约束，可直接作为后续治理日的恢复入口 | 不涉及运行时接口变更 |

### D48-D53 验证结论

- [ ] D48-D52 各阶段都已补单测并维持 quality_gate 绿色，未改变既有 gate metrics 的公开语义
- [ ] quality_gate 在 D49-D52 期间持续保持 `overall_success=True`、`quality_assessment.grade='A'`
- [ ] code_quality 告警基线已在 D52 收回到 44，未因下游消费链治理扩充而新增长期告警债务
- [ ] 当前已知残留为编辑器侧 `yaml` 导入诊断噪声，不影响运行态与质量门结果

### 后续恢复建议

- [ ] 若从 D54 继续，优先寻找“已经消费质量档案但尚未补合同”的相邻 tools 模块，而不是回头改动已闭环的 D49-D52
- [ ] 新阶段优先沿用 `export_*` 单入口模式，避免再次出现多处写盘导致的 metadata 漂移
- [ ] 若需要阶段性复盘，直接从本摘要向上查看 D49-D52 链路表，不必重新遍历各日实现细节

## 50. D54 质量门外相邻治理消费者盘点

- [ ] 将 D54 落成可执行 inventory 资产，而不是仅保留人工盘点结论
- [ ] 优先识别 `tools/` 与仓库根目录编排脚本中已消费质量档案、但尚未具备统一合同字段的相邻治理消费者
- [ ] 将盘点结果同时输出 JSON 与 Markdown，便于后续治理日机器读取与人工恢复
- [ ] 对已完成 D49-D52 合同升级的主链模块保持只读盘点，不再重复纳入 D54 改造目标

### D54 可执行盘点资产

| 资产 | 作用 | 产出 |
| --- | --- | --- |
| `tools/quality_consumer_inventory.py` | 扫描 `tools/` 与仓库根目录编排脚本中的质量档案消费点，并判定是否缺失统一合同 | `output/quality-consumer-inventory.json` + `output/quality-consumer-inventory.md` |
| `tests/unit/test_quality_consumer_inventory.py` | 保障候选识别、合同缺口判定、推荐排序与导出阶段元数据稳定 | D54 回归测试 |

### D54 盘点口径

| 维度 | 规则 |
| --- | --- |
| 识别对象 | `tools/` 下 `.py` 与 `.ps1` 模块，以及仓库根目录下非 `test_*.py` 的 `.py` / `.ps1` 编排脚本 |
| 消费判定 | 发现 `quality-gate`、`quality-assessment`、`continuous-improvement`、`quality-improvement-archive`、`quality-feedback` 等档案引用即视为消费者 |
| 合同完成判定 | 同时具备 `metadata`、`report_metadata`、`analysis_summary`、`failed_operations` 与 `export_contract_version` |
| 推荐优先级 | 直接读档 > 命令编排消费 > 仅引用档案 |

### D54 首轮盘点结论

| 模块 | 消费方式 | 档案输入 | 当前状态 | 作为下一跳的优先级 |
| --- | --- | --- | --- | --- |
| `tools/stage2_s2_1_s2_6_runner.ps1` | 命令编排消费 | `quality-gate`、`quality-assessment`、`continuous-improvement`、`quality-improvement-archive`、`quality-feedback` | 尚未形成统一盘点/执行档案合同 | 中 |
| `tools/stage1_d1_d10_runner.ps1` | 命令编排消费 | D10 与 D49-D54 相关质量档案命令链 | 尚未形成统一盘点/执行档案合同 | 中 |
| D49-D52 主链模块 | 直接读档 | 各自上游质量档案 | 已完成统一合同，仅保留在盘点报告中作为 governed 样本 | 不再纳入 D54 改造 |

### D54 延续约束

- [ ] D54 先做 inventory，不直接重构 runner 编排链，避免把“盘点日”扩成新的大规模 orchestration 改造
- [ ] inventory 工具的推荐结果只服务下一跳决策，不改变现有 quality_gate 与 D49-D52 的兼容字段语义
- [ ] 后续若进入 runner 类治理消费者改造，仍需沿用 `metadata`、`report_metadata`、`analysis_summary`、`failed_operations` 的统一命名

## 55. D59 Inventory 扫描范围扩展

- [ ] 将 quality consumer inventory 的正式扫描范围从 `tools/` 扩展到 `tools/` 加仓库根目录编排脚本，避免根目录 orchestration 入口长期游离在治理清单之外
- [ ] 在不放大到全仓库递归扫描的前提下，只纳入仓库根目录下非 `test_*.py` 的 `.py` / `.ps1` 脚本，控制噪声与误报
- [ ] 通过 `analysis_summary.scan_scope` 和 `governance.quality_consumer_inventory.include_root_scripts` 显式固化新口径，并将合同版本提升到 `d59.v1`

### D59 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| inventory scanner | 新增根目录脚本扫描，继续保留 `tools/` 递归扫描 | 不扩展到 `src/`、`tests/` 等全仓库递归 |
| 配置 | 新增显式 `include_root_scripts: true` 开关 | 默认行为与当前治理目标一致，可按需关闭 |
| 报告摘要 | `analysis_summary` 新增 `scan_scope` | 原有推荐、缺口计数与导出结构保持兼容 |

### D59 验证结论

- [ ] `tests/unit/test_quality_consumer_inventory.py` 已通过，验证根目录脚本被纳入扫描且 `test_*.py` 不会误入清单。
- [ ] 真实运行 `python tools/quality_consumer_inventory.py --root . --output output/quality-consumer-inventory.json --markdown output/quality-consumer-inventory.md` 已通过。
- [ ] 当前仓库根目录实际被扫描到的脚本包含 `generate_test_report.py` 与 `run_cycle_demo.py`，但现阶段没有新增命中质量档案消费模式，因此 inventory 结果仍维持 `missing_contract_count = 0`。

## 56. D60 Inventory 聚合档案识别与根目录观测区补齐

- [ ] 将 inventory 的 artifact pattern 扩展到 `cycle_demo_report`、`autorresearch_report` 等新聚合档案，让根目录编排脚本能以真实消费者身份进入清单，而不是只被扫描但不可见
- [ ] 给 inventory 报告增加 `root_script_observations` 观测区，单独列出“已扫描但未命中消费模式的根目录脚本”，减少扩围后信息黑洞
- [ ] 将 quality consumer inventory 合同版本提升到 `d60.v1`，区分 D59 的扫描范围扩展与本轮的聚合档案识别/观测语义

### D60 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| artifact patterns | 新增 `cycle_demo_report`、`autorresearch_report` 模式，覆盖 `cycle_demo_results_*`、`cycle-demo-report.json`、`autorresearch_report.json` 等聚合档案 | 既有质量主链档案模式不变 |
| root observations | 新增 `root_script_observations` 与 `analysis_summary.root_script_observation_count` | 主 `inventory` 清单仍仅保留真正命中消费模式的消费者 |
| Markdown 报告 | 新增 `Root Script Observations` 区块 | 既有 Summary / Consumers / Recommendation 结构继续保留 |

### D60 验证结论

- [ ] `tests/unit/test_quality_consumer_inventory.py` 已通过，验证 `run_cycle_demo.py` 可因 `cycle_demo_report` 进入消费者清单，且 `autorresearch_report` 模式可识别新的根目录聚合脚本夹具。
- [ ] 报告中的 `root_script_observations` 已覆盖未命中消费模式的根目录脚本，并同步写入 Markdown 的 `Root Script Observations` 区块。
- [ ] 真实运行 inventory 后，`output/quality-consumer-inventory.json` 已升级到 `d60.v1`，并保留 `scan_scope` 与新增观测计数。
- [ ] 对 `generate_test_report.py` 的职责复核结论为“继续保持观测态”：该脚本读取的是 `storage_test_results.json` 并输出存储性能评估报告，不属于当前质量治理链或聚合档案族，因此不新增 artifact pattern。

## 57. D61 AutoResearch Runner 统一治理合同补齐

- [ ] 将 `tools/autorresearch/autorresearch_runner.py` 纳入统一治理合同，补齐顶层 `metadata`、`report_metadata`、`analysis_summary`、`failed_operations`
- [ ] 保留既有 AutoResearch 循环语义、`best_val_bpb=` / `report=` CLI 输出与 history 结构，仅在配置、运行期元数据和最终写盘入口补治理字段
- [ ] 用单一 `export_autorresearch_report` 写盘入口保证 `last_completed_phase` 与真实落盘阶段一致，并让 inventory 消除 `autorresearch_report` 的唯一剩余缺口

### D61 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| runner report | 增加顶层统一治理合同与 `result_schema = autorresearch_runner_report` | 原有 `instruction`、`strategy`、`rollback_mode`、`best_val_bpb`、`history` 不变 |
| runtime tracking | 新增 baseline、iteration、assemble、export 相位元数据与失败落账 | 不改变 heuristic / llm 策略选择与 git rollback 语义 |
| 配置 | 新增 `governance.autorresearch_runner.minimum_stable_improvement_count` 与 `export_contract_version = d61.v1` | 无配置时仍可回退默认值 |

### D61 验证结论

- [ ] `tests/unit/test_autorresearch_runner_contract.py` 已通过，覆盖导出合同、syntax fail 落账、最小 CLI 路径下的 `export_autorresearch_report` 相位一致性，以及真实 git 仓库场景下 `improved_committed` / `improved_no_commit` 两条分支的合同稳定性，并与 `tests/unit/test_quality_consumer_inventory.py` 一起保持绿色。
- [ ] 真实运行 inventory 后，`tools/autorresearch/autorresearch_runner.py` 已从 `missing_contract` 转为 `governed`，`missing_contract_count = 0` 且 `eligible_missing_contract_count = 0`。
- [ ] `output/quality-consumer-inventory.json` 与 Markdown 报告已不再推荐 AutoResearch runner 作为下一跳缺口，`recommended_path = none`。

## 58. D62 Inventory 观测区分类细化

- [x] 在不改变 `root_script_observations` 基本结构与 `no_artifact_match` 语义的前提下，给观测项增加分类层，避免后续根目录观测项增长后可读性快速下降
- [x] 将 `generate_test_report.py` 一类脚本显式归入“非治理域脚本”，把“未命中治理档案模式”和“属于其他业务/验证域”区分开来
- [x] 将 quality consumer inventory 合同版本提升到 `d62.v1`，以反映观测分类与摘要字段的新增

### D62 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| observation payload | 新增 `observation_category`、`observation_category_label` | 原有 `observation_status = no_artifact_match` 保持不变 |
| analysis summary | 新增 `root_script_observation_category_counts` | 原有总数 `root_script_observation_count` 保持不变 |
| Markdown 报告 | 在 `Root Script Observations` 区块增加分类列与分类计数摘要 | 既有 Summary / Consumers / Recommendation 结构继续保留 |

### D62 验证结论

- [x] `tests/unit/test_quality_consumer_inventory.py` 已通过，验证 `generate_test_report.py` 在观测区会被标记为 `non_governance_domain_script / 非治理域脚本`。
- [x] 真实运行 inventory 后，Markdown 的 `Root Script Observations` 已展示分类列与分类计数，后续同类脚本可以按分类聚合阅读。
- [x] `output/quality-consumer-inventory.json` 已升级到 `d62.v1`，并新增 `root_script_observation_category_counts` 字段。

## 59. D63 Inventory 纳入质量主链

- [x] 将 `tools/quality_consumer_inventory.py` 纳入 `tools/quality_gate.py` 主链，避免 inventory 继续停留在旁路治理工具状态
- [x] 让 `tools/quality_feedback.py` 直接消费 inventory 摘要，并把合同缺口或未归类观测转换为优先行动
- [x] 将 `quality_gate` 与 `quality_feedback` 合同版本统一提升到 `d63.v1`，明确反映主链已具备 inventory bridge

### D63 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| quality gate | 新增 `quality_consumer_inventory` gate，并将其结果写入总报告 | 原有 logic / dependency / code / test / assessment / archive / feedback gate 顺序语义保持稳定 |
| quality feedback | 新增 `inventory_summary` 与 inventory 驱动的 `priority_actions` | 原有 failed dimensions、owner notifications、issue drafts 结构不变 |
| 配置 | `governance.quality_gate.export_contract_version` 与 `governance.quality_feedback.export_contract_version` 升级到 `d63.v1` | 既有阈值字段与导出路径约定保持不变 |

### D63 验证结论

- [x] `tests/unit/test_quality_gate.py` 已通过，验证 quality gate 会生成 inventory 工件，并要求 feedback gate 读取 inventory 输入。
- [x] `tests/unit/test_quality_feedback.py` 已通过，验证 inventory healthy/critical 两类状态会映射到 `inventory_summary` 与 `priority_actions`。
- [x] `config.yml` 已同步 `quality_gate`、`quality_feedback` 到 `d63.v1`，避免真实运行时版本回退。

## 60. D64 Inventory 信号沉淀进 Archive

- [x] 将 `tools/quality_improvement_archive.py` 升级为直接消费 inventory 报告，避免 archive 继续只反映旧的 assessment/improvement 两层视角
- [x] 将 quality gate 顺序调整为 inventory 先于 archive，保证 archive 沉淀的是当前真实主链状态而不是缺一环的中间态
- [x] 将 `quality_improvement_archive` 合同版本提升到 `d64.v1`，反映 latest/jsonl/dossier 已新增 inventory 治理摘要

### D64 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| archive latest/jsonl | 新增 `inventory_summary`，并在 `analysis_summary` 中补充 inventory 缺口与未归类统计 | 原有 quality score、trend、failed gates、next cycle targets 字段保持不变 |
| archive markdown dossier | 新增 `Inventory Governance` 区块，展示 inventory 状态、观测分类与推荐下一跳 | 原有 Snapshot / Risks / Improvement Backlog 结构继续保留 |
| quality gate orchestration | inventory gate 前移到 archive gate 之前 | feedback 仍消费 archive latest + inventory，主链末端语义不变 |

### D64 验证结论

- [x] `tests/unit/test_quality_improvement_archive.py` 已通过，验证 latest 与 dossier 都包含 inventory 摘要。
- [x] `tests/unit/test_quality_gate.py` 已通过，验证 archive gate 需要 inventory 输入，并输出 `inventory_summary`。
- [x] 真实运行 `tools/quality_gate.py` 后，最新 archive dossier 已出现 `Inventory Governance` 区块，latest JSON 已沉淀 inventory 统计。

## 61. D65 Inventory 历史趋势沉淀

- [x] 在不改动 continuous improvement 主职责的前提下，让 archive history 基于既有 JSONL 时间线生成 `inventory_trend`
- [x] 将 inventory 历史趋势写入 archive latest/jsonl/dossier，避免 inventory 仍然只有当前快照没有时间序列判断
- [x] 将 `quality_improvement_archive` 合同版本提升到 `d65.v1`，明确反映 archive 已开始追踪 inventory 历史趋势

### D65 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| archive latest/jsonl | 新增 `inventory_trend`，并在 `analysis_summary` 中补充 `inventory_trend_status`、`inventory_history_points` | 原有 `inventory_summary`、quality score、trend、next cycle targets 字段保持不变 |
| archive markdown dossier | 新增 `Inventory Trend` 区块，展示缺口变化、未归类变化与推荐目标是否发生变化 | 原有 Snapshot / Risks / Improvement Backlog / Inventory Governance 结构继续保留 |
| history consumption | 在写新 entry 前读取既有 archive JSONL，选取最近一个带 `inventory_summary` 的 entry 作为趋势基线 | 旧历史行即使没有 inventory 字段也不会阻断新写盘 |

### D65 验证结论

- [x] `tests/unit/test_quality_improvement_archive.py` 已通过，验证 baseline 与 improving 两类 `inventory_trend` 都能从 archive history 中生成。
- [x] `tests/unit/test_quality_gate.py` 已通过，验证 archive gate 输出已包含 `inventory_trend`。
- [x] 真实运行 `tools/quality_gate.py` 后，archive latest 已包含 `inventory_trend`，dossier 已出现 `Inventory Trend` 区块。

## 62. D66 Inventory 趋势转入 Continuous Improvement

- [x] 在不改变 quality gate 主链顺序的前提下，让 `tools/continuous_improvement_loop.py` 读取既有 archive history 中最近的 `inventory_trend`
- [x] 将 inventory 趋势转成 continuous improvement 的 `action_backlog` 与 `next_cycle_targets`，避免 inventory 趋势仍停留在 archive 被动记录层
- [x] 将 `continuous_improvement` 合同版本提升到 `d66.v1`，反映 report 中已新增 inventory follow-up 视图

### D66 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| continuous improvement report | 新增 `inventory_focus`，包含 inventory summary、inventory trend 与 inventory follow-up actions | 原有 `current_snapshot`、score trend、action_backlog、next_cycle_targets 结构保持不变 |
| next cycle targets | 新增 inventory 目标字段，如 `target_inventory_missing_contract_count`、`inventory_trend_status`、`inventory_recommended_next_target` | 原有质量分与 focus dimensions 目标保持不变 |
| analysis summary | 新增 `inventory_trend_status` 与 `inventory_backlog_count` | 原有 current score、history points、backlog count 等字段保持不变 |

### D66 验证结论

- [x] `tests/unit/test_continuous_improvement_loop.py` 已通过，验证 archive history 中的 regressing inventory trend 会转成 inventory follow-up actions 与 targets。
- [x] `tests/unit/test_quality_gate.py` 已通过，验证 quality gate 中的 continuous improvement gate 会读取 archive history 并输出 `inventory_focus`。
- [x] 真实运行 `tools/quality_gate.py` 后，`output/continuous-improvement.json` 已包含 `inventory_focus` 与 inventory targets；在当前绿色状态下 `inventory_backlog_count = 0`，但 inventory trend 已可用于后续回退场景触发动作。

## 63. D67 Runner 仅在 Inventory 回退时暴露治理提示

- [x] 在不改变 stage1/stage2 runner DryRun 与正式执行语义的前提下，只在 `inventory_trend.status = regressing` 时向 runner 汇总报告暴露 `governance_alerts`
- [x] 保持 inventory 稳定或缺失 archive latest 时的零噪音输出，避免常态阶段把治理提示写入 day/stage/global 汇总
- [x] 将 `stage1_runner`、`stage2_runner` 合同版本统一提升到 `d67.v1`，明确反映 runner 已消费 archive latest 的 inventory 趋势

### D67 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| stage1 runner | day/global summary 条件性新增 `governance_alerts`，仅在 inventory 趋势回退时输出 | 原有 `steps`、`pass_rate_percent`、`rollback_tips`、`strict_rollback_flow` 不变 |
| stage2 runner | stage/global summary 条件性新增 `governance_alerts`，仅在 inventory 趋势回退时输出 | 原有 `steps`、`pass_rate_percent`、`target_code_health_percent`、DryRun 语义不变 |
| helper 兼容性 | 读取 `output/quality-improvement-archive-latest.json` 时改用 Windows PowerShell 5.1 兼容的 `ConvertFrom-Json` 调用 | archive latest 现有 JSON 结构不需要改动 |
| 配置 | `governance.stage1_runner.export_contract_version` 与 `governance.stage2_runner.export_contract_version` 升级到 `d67.v1` | 既有阈值字段与导出路径约定保持不变 |

### D67 验证结论

- [x] `tests/unit/test_stage1_runner_contract.py` 已通过，验证 stable/no-file 场景不会输出 `governance_alerts`，regressing 场景会在 global report 暴露治理提示。
- [x] `tests/unit/test_stage2_runner_contract.py` 已通过，验证 stable/no-file 场景不会输出 `governance_alerts`，regressing 场景会在 global report 暴露治理提示。
- [x] 首轮 runner 契约测试暴露了真实兼容性问题：Windows PowerShell 5.1 不支持 `ConvertFrom-Json -Depth`，导致 helper 被 catch 后静默回退为空；修复后 runner 契约测试恢复全绿。

## 64. D68 Inventory 趋势转入 Feedback 分发

- [x] 在不改变 feedback 既有 assessment/improvement/archive/inventory 输入结构的前提下，让 `tools/quality_feedback.py` 直接消费 archive latest 中的 `inventory_trend`
- [x] 仅在 `inventory_trend.status = regressing` 且当前 inventory 快照仍健康时，补发 inventory 趋势型优先行动与 issue draft，避免稳定阶段制造治理噪音
- [x] 将 `quality_feedback` 合同版本提升到 `d68.v1`，反映反馈分发层已能识别 inventory 历史回退而不只盯当前快照

### D68 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| feedback json | 新增 `inventory_trend`，并在 `analysis_summary` 中补充 `inventory_trend_status` | 原有 `inventory_summary`、`priority_actions`、`owner_notifications`、`issue_drafts` 结构保持不变 |
| priority actions | 当 inventory 当前快照健康但趋势回退时，新增 `quality_consumer_inventory_trend` 动作，驱动质量治理 follow-up | 当前存在缺失合同或未归类脚本时，原有 inventory snapshot 动作继续保留 |
| issue drafts | 当 inventory 趋势回退时，在 issue draft 正文中补充 `Inventory Trend` 证据段 | 其他 owner 的 issue draft 模板、文件命名、标签保持不变 |
| 配置 | `governance.quality_feedback.export_contract_version` 升级到 `d68.v1` | 既有阈值字段与导出路径约定保持不变 |

### D68 验证结论

- [x] `tests/unit/test_quality_feedback.py` 已通过，验证 stable inventory trend 不会新增趋势噪音，regressing inventory trend 会触发 `quality_consumer_inventory_trend` action 与质量治理 issue draft。
- [x] `tests/unit/test_quality_gate.py` 已通过，验证 quality gate 末端生成的 feedback 报告已升级到 `d68.v1`，并会透传 archive latest 中的 `inventory_trend`。
- [x] 真实运行 `tools/quality_feedback.py` 后，当前稳定仓库状态下 `output/quality-feedback.json` 已新增 `inventory_trend` 与 `analysis_summary.inventory_trend_status`，且没有额外生成 inventory 趋势型优先行动。

## 65. D69 Stable/Regressing 端到端对照回归固化

- [x] 基于同一套 `archive latest` 输入，新增 stable / regressing 两类端到端对照回归，统一验证 feedback 与 stage runner 的信号抬升策略
- [x] 固化 stable 场景下的零噪音约束：feedback 不生成 inventory 趋势型 action/issue draft，runner 不生成 `governance_alerts`
- [x] 固化 regressing 场景下的一致抬升约束：feedback 生成 inventory 趋势型 action/issue draft，runner global report 暴露 `governance_alerts`

### D69 回归资产范围

| 范围 | 新增资产 | 保持兼容 |
| --- | --- | --- |
| end-to-end regression | 新增 `tests/unit/test_inventory_signal_end_to_end.py`，在临时工作区同时驱动 `quality_feedback.py`、`stage1_d1_d10_runner.ps1`、`stage2_s2_1_s2_6_runner.ps1` | 不改动现有生产合同与导出字段 |
| stable 对照 | 验证 `inventory_trend.status = stable` 时 feedback/runners 都保持安静 | D68/D67 既有单点契约测试继续保留 |
| regressing 对照 | 验证 `inventory_trend.status = regressing` 时 feedback 与 runners 同步抬升治理信号 | 不改变原有 recommended target 与 alert 类型命名 |

### D69 验证结论

- [x] `tests/unit/test_inventory_signal_end_to_end.py` 已通过，验证 stable archive latest 会同时压住 feedback 与 runner 的治理噪音。
- [x] `tests/unit/test_inventory_signal_end_to_end.py` 已通过，验证 regressing archive latest 会同时抬升 feedback 的 `quality_consumer_inventory_trend` 与 runner 的 `governance_alerts`。
- [x] 联合回归 `tests/unit/test_inventory_signal_end_to_end.py`、`tests/unit/test_quality_feedback.py`、`tests/unit/test_stage1_runner_contract.py`、`tests/unit/test_stage2_runner_contract.py` 已通过，汇总结果 `37 passed, 0 failed`。

## 66. D70 Quality Gate 全链真实回放

- [x] 将 stable / regressing 两类样本继续扩到 `quality_gate` 主链真实回放，不再只验证 feedback + runner 的局部链路
- [x] 让 quality gate 在临时工作区中自产生 inventory、continuous improvement、archive、feedback，再接 stage runner dry-run，验证五端一致性来自主链真实产物
- [x] 在实际仓库执行一次 stable 全链回放，确认五端一致性不只在临时工作区成立

### D70 回放资产范围

| 范围 | 新增资产 | 保持兼容 |
| --- | --- | --- |
| quality gate replay | 新增 `tests/unit/test_inventory_signal_quality_gate_replay.py`，在临时工作区通过 `python -m tools.quality_gate` 真实生成 `quality-gate`、inventory、continuous improvement、archive、feedback 工件 | 不改动 `quality_gate.py` 既有编排顺序与合同版本 |
| stable 回放 | 验证 `quality_gate` stable 运行后，inventory / continuous improvement / archive / feedback / runners 五端保持一致且 runner 无 `governance_alerts` | D69 的局部对照回归继续保留 |
| regressing 回放 | 验证引入缺失合同消费者后，`quality_gate` 会生成 regressing archive latest，并联动 feedback 与 runners 抬升治理信号 | 不改变现有 alert 类型与 feedback 动作命名 |
| actual workspace replay | 在当前仓库真实执行 `tools/quality_gate.py` + stage runner dry-run，确认 stable 五端一致性 | 不引入额外 mock 或临时补丁 |

### D70 验证结论

- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已通过，验证 stable quality gate replay 会同时压住 feedback 趋势动作与 runner `governance_alerts`。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已通过，验证 regressing quality gate replay 会在 inventory / archive / feedback / runners 四端同步抬升治理信号，并使 `quality_gate` 总结果按预期失败退出。
- [x] 联合回归 `tests/unit/test_inventory_signal_quality_gate_replay.py`、`tests/unit/test_inventory_signal_end_to_end.py`、`tests/unit/test_quality_feedback.py`、`tests/unit/test_stage1_runner_contract.py`、`tests/unit/test_stage2_runner_contract.py` 已通过，汇总结果 `41 passed, 0 failed`。
- [x] 真实运行 `tools/quality_gate.py` 后，当前仓库 stable 状态满足：`quality-consumer-inventory.missing_contract_count = 0`、`continuous-improvement.inventory_focus.trend_status = stable`、`quality-improvement-archive-latest.inventory_trend.status = stable`、`quality-feedback.inventory_trend.status = stable`，且 stage1/stage2 全局 dry-run 报告均不包含 `governance_alerts`。

## 67. D71 Issue Index + Archive Dossier 并入全链真实回放

- [x] 将 `quality-feedback-issues.json` 与 archive `dossier_path` 一并纳入 `quality_gate` stable/regressing 真实回放，避免七端护栏仍只验证 JSON 主报告层
- [x] 固化 stable 场景下的附属端零噪音约束：issue index 仅保留既有 `module-owners` backlog，dossier 明确记录 `Inventory Trend = stable`，runner 继续无 `governance_alerts`
- [x] 固化 regressing 场景下的附属端一致抬升约束：issue index 出现 `quality-governance` draft，archive dossier 写出 `Inventory Trend = regressing` 与缺口证据，并继续与 feedback / runners 同步抬升

### D71 回放资产范围

| 范围 | 新增断言 | 保持兼容 |
| --- | --- | --- |
| issue index | 在 `tests/unit/test_inventory_signal_quality_gate_replay.py` 中读取 `quality-feedback.json.report_metadata.issue_index_path`，对 stable/regressing 两态分别断言 issue draft owner 分布 | 不改动 feedback issue draft 生成逻辑与文件命名 |
| archive dossier | 在同一回放测试中读取 `quality-improvement-archive-latest.json.report_metadata.dossier_path`，断言 `Inventory Trend` 章节与 stable/regressing 证据文本 | 不改动 archive latest/dossier 的导出结构 |
| seven-end consistency | 将原五端一致性扩展为 inventory / continuous improvement / archive latest / archive dossier / feedback / feedback issue index / runners 七端一致性 | D69 的 feedback+runner 对照与 D70 的主链回放测试继续保留 |
| actual workspace replay | 在当前仓库真实执行 `tools/quality_gate.py` + stage runner dry-run，复核 stable 仓库下 issue index 与 dossier 也保持低噪音稳定输出 | 不引入额外 mock、手工 latest 注入或运行态特判 |

### D71 验证结论

- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已升级为七端回放测试，stable 场景下已断言 `issue_index.count = 1`、唯一 owner 为 `module-owners`、archive dossier 含 `Inventory Trend` 且为 `stable`、stage1/stage2 全局报告无 `governance_alerts`。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已升级为七端回放测试，regressing 场景下已断言 issue index 出现 `quality-governance` draft，archive dossier 写出 `Trend Status: regressing` 与 `Missing Contracts: 1`，且 feedback / runners 同步抬升治理信号。
- [x] 联合回归 `tests/unit/test_inventory_signal_quality_gate_replay.py`、`tests/unit/test_inventory_signal_end_to_end.py`、`tests/unit/test_quality_feedback.py` 已通过，汇总结果 `23 passed, 0 failed`。
- [x] 真实运行 `tools/quality_gate.py` 后，当前仓库 stable 状态满足：`output/quality-feedback-issues.json.count = 1` 且唯一 owner 为 `module-owners`；最新 archive dossier 已写出 `Inventory Trend` 且 `Trend Status: stable`；stage1/stage2 全局 dry-run 报告仍不包含 `governance_alerts`。

## 68. D72 Issue Draft Markdown 正文并入全链真实回放

- [x] 将 issue draft Markdown 正文并入 `quality_gate` stable/regressing 真实回放，避免九端护栏仍只在 issue index 元信息层止步
- [x] 固化 stable 场景下的正文零噪音约束：既有 `module-owners` draft 只保留 `Summary`、`Action Items`、`Acceptance`，正文不应出现 `Inventory Trend` 区块
- [x] 固化 regressing 场景下的正文证据约束：`quality-governance` draft 必须带 `Inventory Trend` 区块，并写出 regressing 状态与 `Recommended Next Target`

### D72 回放资产范围

| 范围 | 新增断言 | 保持兼容 |
| --- | --- | --- |
| issue draft markdown body | 在 `tests/unit/test_inventory_signal_quality_gate_replay.py` 中根据 issue index 逐个读取 Markdown 正文，stable/regressing 两态分别断言正文结构与证据字段 | 不改动 `quality_feedback.py` 的 issue draft 模板、文件命名与索引结构 |
| nine-end consistency | 将原七端一致性进一步扩展为 inventory / continuous improvement / archive latest / archive dossier / feedback / feedback issue index / feedback issue draft body / stage1 runner / stage2 runner 九端一致性 | D71 的索引层与 dossier 层断言继续保留 |
| actual workspace evidence | 复核当前仓库 stable 的 `output/quality-feedback-issues/quality-action-module-owners.md`，确认正文保留 `Trend: stable` 与 backlog 行动，但无 `Inventory Trend` 噪音区块 | 不需要额外重跑或修改生产导出逻辑 |

### D72 验证结论

- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已升级为九端回放测试，stable 场景下已断言 `module-owners` issue draft Markdown 正文包含 `## Summary`、`- Trend: stable`，且不包含 `## Inventory Trend`。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已升级为九端回放测试，regressing 场景下除 `quality-governance` draft 外，也已细粒度断言 `module-owners` draft 正文包含 `## Summary`、`- Owner: module-owners`、`- Trend: stable`、`## Inventory Trend`、`code_health` 行动项与 `## Acceptance`，防止非治理 owner 正文结构漂移。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已升级为九端回放测试，regressing 场景下已断言 `quality-governance` issue draft Markdown 正文包含 `## Inventory Trend`、`- Status: regressing`、`- Recommended Next Target: tools/missing_consumer.py` 与 `## Action Items`。
- [x] 联合回归 `tests/unit/test_inventory_signal_quality_gate_replay.py`、`tests/unit/test_inventory_signal_end_to_end.py`、`tests/unit/test_quality_feedback.py` 已通过，汇总结果 `23 passed, 0 failed`。
- [x] 当前仓库 stable 的 `output/quality-feedback-issues/quality-action-module-owners.md` 已确认正文保持低噪音：仅含 `Summary / Action Items / Acceptance` 主体，不包含 `Inventory Trend` 区块。

## 69. D73 Uncategorized Root Script 回退路径与正文分流护栏

- [x] 将 `uncategorized_root_script` 做成第二条 regressing 回放路径，避免当前回退护栏只覆盖 `missing_contract` 一种 inventory 退化模式
- [x] 在同一套 `quality_gate` 真实回放里对比 `missing_contract` 与 `uncategorized_root_script` 两条 regressing 路径的 issue draft Markdown 正文，防止九端一致但语义分流错误
- [x] 同时锁定 `module-owners` 与 `quality-governance` 两类 owner 的正文差异，确保非治理 owner 不会意外吞掉治理 owner 的行动语义，反之亦然

### D73 回放资产范围

| 范围 | 新增断言 | 保持兼容 |
| --- | --- | --- |
| uncategorized replay path | 在 `tests/unit/test_inventory_signal_quality_gate_replay.py` 中新增 `uncategorized_regressing` 临时工作区场景，通过真实根目录未归类脚本触发 `uncategorized_root_script = 1` 与 inventory trend regressing | 不改动 `quality_consumer_inventory.py` 现有分类规则与生产导出逻辑 |
| semantic split checks | 对比 `missing_contract` 与 `uncategorized_root_script` 两条路径下的 `module-owners` / `quality-governance` issue draft 正文，分别断言推荐目标、行动语句与证据段文本差异 | D72 的 stable/regressing 主体断言继续保留 |
| archive + runner alignment | 同时断言 dossier 中 `Missing Contracts` 与 `Uncategorized Root Script Delta` 的分流，以及 stage runner `recommended_next_target` 在两条路径下的不同输出 | 不改变 D67 runner alert 结构与 D65 archive dossier 结构 |

### D73 验证结论

- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已新增 `uncategorized_root_script` 的 regressing 回放路径，并验证 inventory 摘要从 `missing_contract_count = 1 / uncategorized = 0` 与 `missing_contract_count = 0 / uncategorized = 1` 两种状态都能稳定进入主链回放。
- [x] 同一测试已断言 `module-owners` draft 在两条路径下都保留 `code_health` 正文骨架，但 `Recommended Next Target` 会按 `tools/missing_consumer.py` 与 `none` 正确分流。
- [x] 同一测试已断言 `quality-governance` draft 在 `missing_contract` 路径下包含“补齐缺失合同的质量消费者”，在 `uncategorized_root_script` 路径下包含“为未归类的根目录脚本补齐 observation 分类”，两者不会交叉污染。
- [x] 联合回归 `tests/unit/test_inventory_signal_quality_gate_replay.py`、`tests/unit/test_inventory_signal_end_to_end.py`、`tests/unit/test_quality_feedback.py`、`tests/unit/test_quality_consumer_inventory.py` 已通过，汇总结果 `31 passed, 0 failed`。

## 70. D74 真实仓库 Uncategorized 回放与 Feedback Markdown 分流护栏

- [x] 在真实仓库临时注入一枚根目录未归类脚本样本，执行 `tools/quality_gate.py` + stage1/stage2 dry-run，验证 `uncategorized_root_script` 回退路径不只在临时工作区成立
- [x] 将 `missing_contract` 与 `uncategorized_root_script` 两条 regressing 路径的 `feedback Markdown` 总报告也纳入差异断言，避免九端一致但报告层语义仍发生串线
- [x] 回放结束后删除真实仓库样本并再次执行 stable 链，使当前仓库输出重新收敛到 stable 常态

### D74 回放资产范围

| 范围 | 新增验证 | 保持兼容 |
| --- | --- | --- |
| actual workspace uncategorized replay | 在当前仓库临时加入 `inventory_probe_uncategorized_root_script.py`，验证真实 `quality_consumer_inventory` 输出 `uncategorized_root_script_count = 1`，`quality_feedback` 生成 `module-owners + quality-governance` 双 owner，runner `recommended_next_target = null` | 不改动生产分类规则；样本在验证后已删除 |
| feedback markdown split | 在 `tests/unit/test_inventory_signal_quality_gate_replay.py` 中新增 `feedback Markdown` 差异断言：`missing_contract` 路径必须写出 `Missing Contracts: 1` 与“补齐缺失合同的质量消费者”，`uncategorized_root_script` 路径必须写出 `Missing Contracts: 0`、`Uncategorized Root Script Delta: 1` 与“为未归类的根目录脚本补齐 observation 分类” | D73 的 issue draft 正文差异断言继续保留 |
| stable restore | 实际回放后再次执行 stable 链，确认当前仓库重新回到 `inventory_trend.status = stable`、`quality_feedback` 仅保留 `module-owners`、stage1/stage2 全局 dry-run 无 `governance_alerts` | 不需要额外回滚历史文件或手工改写产物 |

### D74 验证结论

- [x] 真实仓库 uncategorized 样本回放已验证：`quality-gate overall_success = False`，`quality_consumer_inventory.uncategorized_root_script_count = 1`，`quality-feedback.md` 同时出现 `module-owners` 与 `quality-governance`，archive latest 中 `inventory_trend.status = regressing` 且 `uncategorized_root_script_delta = 1`，stage1/stage2 全局 dry-run 报告均出现 `governance_alerts` 且 `recommended_next_target = null`。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已新增 `feedback Markdown` 分流断言，明确区分 `missing_contract` 路径与 `uncategorized_root_script` 路径下的 `Inventory Summary`、`Inventory Trend` 与 `Priority Actions` 文本。
- [x] 联合回归 `tests/unit/test_inventory_signal_quality_gate_replay.py`、`tests/unit/test_inventory_signal_end_to_end.py`、`tests/unit/test_quality_feedback.py`、`tests/unit/test_quality_consumer_inventory.py` 已通过，汇总结果 `31 passed, 0 failed`。
- [x] 真实仓库当前已恢复到 stable 常态：`output/quality-feedback.md` 显示 `Inventory Trend = stable`、`Missing Contracts = 0`、`Root Observations = 1`；最新 stage1/stage2 全局 dry-run 报告不包含 `governance_alerts`。

## 71. D75 Trend-Only 真实仓库回放与 Owner Action 顺序护栏

- [x] 在真实仓库中补一组“recommended_next_target changed but snapshot healthy”的可控 trend-only 样本，通过受控注入 `quality-improvement-archive-latest.json` 验证该语义分流不只存在于临时工作区
- [x] 将 feedback JSON 与 feedback Markdown 的 owner 级 action 顺序显式锁定，避免后续内容一致但排序漂移造成的人审噪音
- [x] 回放结束后重新执行 stable 质量链并清理临时备份，使当前仓库 latest 输出重新回到 stable 常态

### D75 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| real workspace trend-only replay | 在当前仓库备份并受控改写 `output/quality-improvement-archive-latest.json`，构造 `inventory_summary.status = healthy`、`inventory_trend.status = regressing`、`recommended_next_target_changed = true` 的真实 trend-only 样本，再回放 `tools/quality_feedback.py` + stage1/stage2 dry-run | 不改动 `quality_gate.py` / archive 趋势计算逻辑；样本验证后已重新跑 stable 主链恢复 |
| feedback JSON ordering | 在 `tools/quality_feedback.py` 中为 `priority_actions` 与 `owner_notifications[].todos` 引入稳定排序键，并新增单测锁定 owner 与 action 次序 | 既有 owner 分组、issue draft 模板与 action 文本保持不变 |
| feedback Markdown ordering | `output/quality-feedback.md` 的 `Owner Notifications` 章节现在展开同一顺序的 owner todo 明细，并新增单测/端到端断言验证 module-owners 与 quality-governance 的稳定先后顺序 | 既有 `Priority Actions`、inventory summary/trend、headline 结构保持不变 |

### D75 验证结论

- [x] `tests/unit/test_quality_feedback.py` 已新增排序护栏，断言 `owner_notifications` 按 owner 稳定排序，且同 owner 下的 `todos` 按 priority/dimension/action 稳定输出；对应 Markdown 也按同一顺序展开。
- [x] `tests/unit/test_inventory_signal_end_to_end.py` 已显式固化 trend-only 场景，验证 `inventory_summary = healthy`、`inventory_trend = regressing` 时 feedback 生成 `quality_consumer_inventory_trend`、Markdown 写出 owner todo 明细、stage1/stage2 同步暴露 `governance_alerts`。
- [x] 联合回归 `tests/unit/test_quality_feedback.py`、`tests/unit/test_inventory_signal_end_to_end.py`、`tests/unit/test_inventory_signal_quality_gate_replay.py` 已通过，汇总结果 `33 passed, 0 failed`。
- [x] 真实仓库 trend-only 样本回放已验证：在注入后的 latest 上，`output/quality-feedback.json` 从单一 `module-owners` 扩展为 `module-owners -> quality-governance` 两个 owner，`output/quality-feedback.md` 以同一顺序展开 owner todo，stage1/stage2 全局 dry-run 报告均出现 `governance_alerts` 且 `recommended_next_target = tools/missing_consumer.py`；随后重跑 stable 主链后，当前仓库 latest 输出已恢复到 `Inventory Trend = stable` 且 runner 无治理告警。

## 72. D76 Stable Target Change 抑噪样本与 Issue Draft 顺序护栏

- [x] 新增一类“`previous_recommended_next_target` changed，但 `inventory_trend = stable`”的抑噪样本，证明推荐目标变化本身不会误抬升治理提示
- [x] 将 issue draft Markdown 的 action 顺序也显式锁键，避免 JSON / Markdown 主报告稳定但 issue draft 正文顺序漂移，继续制造人审噪音
- [x] 在真实仓库完成一次 stable-target-change 可控样本回放，并在验证后恢复 stable 主链产物

### D76 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| quiet-signal regression | 在 `tests/unit/test_inventory_signal_end_to_end.py` 中新增 `inventory_trend.status = stable` 且 `recommended_next_target_changed = true` 的样本，验证 feedback 只保留常规 `module-owners` 行动，不会误生 `quality_consumer_inventory_trend` 或 runner `governance_alerts` | 不改动 D75 已建立的 trend-only regressing 抬升逻辑 |
| issue draft ordering | 在 `tools/quality_feedback.py` 中为 issue draft 使用与 owner todos 相同的稳定排序键，并新增单测断言 Markdown 正文中的 action 行顺序 | 不改动 issue draft 模板结构、文件命名与 labels |
| real workspace quiet sample | 在当前仓库受控改写 latest + inventory recommendation，构造 `Recommended Next Target = tools/missing_consumer.py`、`inventory_trend.status = stable`、`recommended_next_target_changed = true` 的真实静默样本，再回放 feedback + stage1/stage2 dry-run | 验证后已重跑 stable 质量链并删除备份，不保留临时样本文件 |

### D76 验证结论

- [x] `tests/unit/test_quality_feedback.py` 已新增 stable-target-change 抑噪断言，验证 `recommended_next_target_changed = true` 且 `inventory_trend = stable` 时，不会生成 `quality_consumer_inventory_trend` action 或 `quality-governance` issue draft。
- [x] `tests/unit/test_quality_feedback.py` 已新增 issue draft 正文顺序断言，验证同 owner 的多条 action 在 draft Markdown 中按稳定键输出。
- [x] `tests/unit/test_inventory_signal_end_to_end.py` 已新增静默端到端样本，验证 `output/quality-feedback.md` 会写出 `Recommended Next Target: tools/missing_consumer.py`，但 stage1/stage2 全局 dry-run 报告仍不包含 `governance_alerts`。
- [x] 联合回归 `tests/unit/test_quality_feedback.py`、`tests/unit/test_inventory_signal_end_to_end.py`、`tests/unit/test_inventory_signal_quality_gate_replay.py` 已通过，汇总结果 `39 passed, 0 failed`。
- [x] 真实仓库静默样本回放已验证：在注入后的 stable latest 与 inventory recommendation 上，`output/quality-feedback.json` / `output/quality-feedback.md` 显示 `Recommended Next Target = tools/missing_consumer.py` 且 `inventory_trend.status = stable`，但仍只有 `module-owners` 一个 owner，issue draft 不新增治理正文，stage1/stage2 全局 dry-run 报告均无 `governance_alerts`；随后重跑 stable 主链后，当前仓库 latest 输出已恢复到 `recommended_next_target = null`、`inventory_trend.status = stable`。

## 73. D77 Issue Index 顺序同构与 Improving Recovery 抑噪样本

- [x] 将 `quality-feedback-issues.json.items` 的顺序也显式锁键，避免 issue index 继续依赖隐式迭代顺序，导致其与 feedback JSON / feedback Markdown / issue draft Markdown 的 owner 顺序漂移
- [x] 再补一类“`inventory_trend = improving` 且 `recommended_next_target_changed = true`”的恢复态静默样本，证明恢复态也不会误抬升治理提示
- [x] 在真实仓库完成一次 improving-target-change 可控样本回放，并在验证后恢复 stable 主链产物

### D77 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| issue index ordering | 在 `tools/quality_feedback.py` 中为 issue draft 与 issue index item 共用显式排序键，并新增单测断言 `quality-feedback-issues.json.items` 顺序与 owner notifications / issue drafts 完全同构 | 不改动 issue draft 文件名、labels、正文模板 |
| improving quiet sample | 在 `tests/unit/test_quality_feedback.py` 与 `tests/unit/test_inventory_signal_end_to_end.py` 中新增 `inventory_trend.status = improving` 且 `recommended_next_target_changed = true` 的样本，验证反馈只保留常规 `module-owners` 行动，runner 仍无 `governance_alerts` | 不改动 D75 trend-only regressing 与 D76 stable-target-change quiet 的既有逻辑 |
| real workspace improving replay | 在当前仓库受控改写 latest + inventory recommendation，构造 `Recommended Next Target = tools/missing_consumer.py`、`inventory_trend.status = improving`、`recommended_next_target_changed = true` 的真实恢复态样本，再回放 feedback + stage1/stage2 dry-run | 验证后已重跑 stable 质量链并删除备份，不保留临时样本文件 |

### D77 验证结论

- [x] `tests/unit/test_quality_feedback.py` 已新增 improving recovery 抑噪断言，并扩展排序护栏，验证 `quality-feedback-issues.json.items` 的 owner 顺序与 feedback JSON / Markdown / issue draft 一致。
- [x] `tests/unit/test_inventory_signal_end_to_end.py` 已新增 improving recovery 端到端样本，验证 `output/quality-feedback.md` 会写出 `Inventory Trend: improving` 与 `Recommended Next Target: tools/missing_consumer.py`，但 stage1/stage2 全局 dry-run 报告仍不包含 `governance_alerts`。
- [x] 联合回归 `tests/unit/test_quality_feedback.py`、`tests/unit/test_inventory_signal_end_to_end.py`、`tests/unit/test_inventory_signal_quality_gate_replay.py` 已通过，汇总结果 `45 passed, 0 failed`。
- [x] 真实仓库恢复态样本回放已验证：在注入后的 improving latest 与 inventory recommendation 上，`output/quality-feedback.json` / `output/quality-feedback.md` 显示 `Recommended Next Target = tools/missing_consumer.py` 且 `inventory_trend.status = improving`，但仍只有 `module-owners` 一个 owner，`quality-feedback-issues.json` 仍只含单个 `module-owners` 项，stage1/stage2 全局 dry-run 报告均无 `governance_alerts`；随后重跑 stable 主链后，当前仓库 latest 输出已恢复到 `recommended_next_target = null`、`inventory_trend.status = stable`。

## 74. D78 Improving Recovery 九端回放与跨文件引用顺序护栏

- [x] 将 improving recovery quiet 语义并入 `quality_gate` replay harness，使 `inventory_trend = improving` 且 `recommended_next_target_changed = true` 的恢复态也在九端真实回放中显式固化
- [x] 继续补“顺序同构”的剩余表面，让 feedback JSON 的 `issue_drafts` 直接带上稳定的真实 `file` 引用与 `index_position`，并由 issue index 反向校准，形成跨文件引用顺序护栏
- [x] 在真实仓库 stable 链重新导出当前反馈产物，使新的派生索引字段落到最新 `output/quality-feedback.json`

### D78 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| improving recovery replay | 在 `tests/unit/test_inventory_signal_quality_gate_replay.py` 中新增受控 quiet recovery 回放：先跑 stable `quality_gate` 主链，再受控注入 improving latest / inventory / continuous improvement / archive dossier，最后回放 feedback + stage1/stage2，验证九端在恢复态下仍保持静默 | 不改动 archive 对 recommended target 的生产计算逻辑；该样本仅用于 replay harness 的受控验证 |
| cross-file reference ordering | 在 `tools/quality_feedback.py` 中为 `issue_drafts` 增加 `file` 与 `index_position`，并使用 issue index 已排序 items 反向校准反馈 JSON 的派生索引顺序 | 不改动 issue draft 文件内容、issue index 结构与现有 Markdown 模板 |
| label/path normalization | 对 issue draft labels 和 file path 统一做稳定排序与斜杠规范化，避免跨平台或后续标签扩展造成表面漂移 | 不改动现有 owner、title、template 的语义 |

### D78 验证结论

- [x] `tests/unit/test_quality_feedback.py` 已扩展断言，验证 feedback JSON 的 `issue_drafts` 与 `quality-feedback-issues.json.items` 在 `owner/title/file/index_position` 上完全同构。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已新增 improving recovery 九端回放，验证 inventory、continuous improvement、archive latest、archive dossier、feedback、issue index、issue draft body、stage1 runner、stage2 runner 在恢复态下仍保持 quiet 语义，且无 `quality_consumer_inventory_trend` 与 `governance_alerts`。
- [x] 联合回归 `tests/unit/test_quality_feedback.py`、`tests/unit/test_inventory_signal_end_to_end.py`、`tests/unit/test_inventory_signal_quality_gate_replay.py` 已通过，汇总结果 `48 passed, 0 failed`。
- [x] 真实仓库 stable 主链已重跑，当前 `output/quality-feedback.json` 的 `issue_drafts` 已带 `file` 与 `index_position`，最新 stage1/stage2 全局 dry-run 报告仍不包含 `governance_alerts`。

## 75. D79 Report Metadata 派生引用列表与 Target-Cleared Recovery 对应样本

- [x] 将更多 `report_metadata` 内的派生引用列表纳入同构护栏，避免当前只锁正文与 issue 链，而下游仍需自行重建稳定引用顺序
- [x] 为 quiet recovery 再补一类“`inventory_trend = improving` 且 `recommended_next_target_changed = true`，但 `recommended_next_target` 被清空为 `none`”的恢复变体，并让 replay harness 与真实仓库受控样本形成一一对应
- [x] 在真实仓库完成一次 target-cleared recovery 可控样本回放，并在验证后恢复 stable 主链产物

### D79 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| report_metadata derived references | 在 `tools/quality_feedback.py` 的 `report_metadata` 中新增 `issue_draft_owners`、`issue_draft_titles`、`issue_draft_files`，并统一复用 issue index 已排序 items 作为来源 | 不改动既有 `issue_index_path`、`issue_dir`、`output_path`、`markdown_path` 字段名 |
| path normalization | `report_metadata` 中的 `output_path`、`markdown_path`、`issue_index_path`、`issue_dir` 统一做斜杠规范化，减少跨平台路径表现漂移 | 不改变路径指向，仅统一文本表示 |
| target-cleared recovery replay | 在 `tests/unit/test_inventory_signal_quality_gate_replay.py` 中新增 improving recovery with target cleared 的九端 quiet 回放，验证 target 从 `tools/missing_consumer.py` 清空为 `none` 后，feedback 与 runner 仍保持静默 | 不改动 regressing / stable / improving-target-change 的既有语义 |
| real workspace target-cleared sample | 在当前仓库受控改写 latest + inventory recommendation，构造 `inventory_trend.status = improving`、`recommended_next_target_changed = true`、`previous_recommended_next_target = tools/missing_consumer.py`、`current_recommended_next_target = null` 的真实恢复态样本，再回放 feedback + stage1/stage2 dry-run | 验证后已重跑 stable 质量链并删除备份，不保留临时样本文件 |

### D79 验证结论

- [x] `tests/unit/test_quality_feedback.py` 已扩展断言，验证 `report_metadata.issue_draft_owners / issue_draft_titles / issue_draft_files` 与 `quality-feedback-issues.json.items` 完全同构。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已新增 improving recovery with target cleared 的九端 quiet 回放，验证 inventory、continuous improvement、archive latest、archive dossier、feedback、issue index、issue draft body、stage1 runner、stage2 runner 在 target cleared 恢复态下仍保持 quiet 语义。
- [x] 联合回归 `tests/unit/test_quality_feedback.py`、`tests/unit/test_inventory_signal_end_to_end.py`、`tests/unit/test_inventory_signal_quality_gate_replay.py` 已通过，汇总结果 `51 passed, 0 failed`。
- [x] 真实仓库 target-cleared recovery 样本回放已验证：在注入后的 improving latest 与 inventory recommendation 上，`output/quality-feedback.json` / `output/quality-feedback.md` 显示 `recommended_next_target = null` 且 `inventory_trend.status = improving`，但仍只有 `module-owners` 一个 owner，最新 stage1/stage2 全局 dry-run 报告均无 `governance_alerts`；随后重跑 stable 主链后，当前仓库 latest 输出已恢复到 `recommended_next_target = null`、`inventory_trend.status = stable`，且备份文件已清理。

## 76. D80 多模块 Report Metadata 派生引用列表与 Recovery 三层对齐

- [x] 将 feedback 之外的治理模块也纳入 `report_metadata` 派生引用列表护栏，避免下游只能依赖单个显式路径字段重建稳定引用顺序
- [x] 为 `continuous_improvement`、`quality_improvement_archive`、`quality_gate` 统一补充稳定的 `artifact_reference_labels / artifact_reference_paths`，并让 `quality_gate` 额外暴露 `gate_names`
- [x] 将 `improving-target-cleared` quiet recovery 从“真实仓库受控样本 + quality_gate replay harness”补齐到 end-to-end，形成三层一一对应

### D80 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| continuous_improvement report_metadata | 新增 `artifact_reference_labels = [history, output]` 与同序 `artifact_reference_paths` | 既有 `history_path`、`output_path` 字段保留，仅补稳定派生列表 |
| quality_improvement_archive report_metadata | 新增 `artifact_reference_labels = [history, latest_output, dossier]` 与同序 `artifact_reference_paths` | 既有 `history_path`、`latest_output_path`、`dossier_path` 字段保留，仅补稳定派生列表 |
| quality_gate report_metadata | 新增 `gate_names` 以及从 `results[*].details` 稳定导出的 `artifact_reference_labels / artifact_reference_paths` | 不改动既有 `results`、`analysis_summary` 与各 gate 明细结构 |
| end-to-end recovery | 在 `tests/unit/test_inventory_signal_end_to_end.py` 中新增 improving-target-cleared quiet 场景，补齐真实仓库受控样本、end-to-end、replay harness 三层一致性 | 不改动 stable / regressing / improving-target-change 的既有断言 |

### D80 验证结论

- [x] `tests/unit/test_continuous_improvement_loop.py`、`tests/unit/test_quality_improvement_archive.py`、`tests/unit/test_quality_gate.py` 已新增断言，验证新增 `report_metadata` 派生引用列表与 gate 顺序稳定输出。
- [x] `tests/unit/test_inventory_signal_end_to_end.py` 已新增 improving-target-cleared quiet 样本，验证 target 从 `tools/missing_consumer.py` 清空为 `none` 时，feedback 与 stage runner 仍保持 quiet。
- [x] 新增字段均复用既有 canonical source 顺序导出，不引入新的排序语义分叉：continuous_improvement 以 history/output 为准，archive 以 history/latest/dossier 为准，quality_gate 以 gate 执行顺序及 gate 内 detail key 稳定顺序为准。

## 77. D81 多模块 Metadata 派生引用列表主链回放护栏

- [x] 将 D80 新增的 `artifact_reference_labels / artifact_reference_paths / gate_names` 从单模块单测推进到 `quality_gate` replay harness，避免仅局部函数正确而主链装配漂移
- [x] 在 stable / regressing / improving / improving-target-cleared 四类回放场景中统一校验 `continuous_improvement`、`quality_improvement_archive`、`quality_gate` 的 metadata 派生引用列表
- [x] 刷新真实仓库主链产物，使 `output/quality-gate.json`、`output/continuous-improvement.json`、`output/quality-improvement-archive-latest.json` 落到最新合同字段

### D81 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| quality_gate replay harness | 新增 `_assert_multimodule_metadata_reference_lists(...)`，统一断言 gate / continuous improvement / archive 三模块 metadata 派生引用列表 | 不改动既有九端语义分流、issue draft、runner alert 断言 |
| stable / regressing / improving quiet replay | 在四类关键样本上重复验证 metadata 引用列表，避免只在单一 happy path 成立 | 不改变既有 loud/quiet 判定条件 |
| real workspace outputs | 通过真实 `quality_gate` 重跑刷新主链产物，保证工作区输出文件已包含新字段 | 不引入新的真实仓库受控注入样本 |

### D81 验证结论

- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已扩展到同时校验 `continuous_improvement.report_metadata.artifact_reference_*`、`quality_improvement_archive.report_metadata.artifact_reference_*` 与 `quality_gate.report_metadata.gate_names / artifact_reference_*`。
- [x] 同一套 metadata 护栏已在 stable、regressing、improving-target-change、improving-target-cleared 四类回放样本上复用，确保不是单场景偶然成立。
- [x] 真实工作区已重跑主链输出，后续人工复核可直接从 `output/quality-gate.json`、`output/continuous-improvement.json`、`output/quality-improvement-archive-latest.json` 查看最新字段。

## 78. D82 Gate Artifact 与下游工件路径同构护栏

- [x] 把 D81 的“metadata 派生列表存在性”进一步推进为“gate artifact 引用与下游真实工件 report_metadata 路径同构”护栏
- [x] 统一补齐 `quality_assessment.report_metadata.output_path` 的斜杠规范化，避免 gate 与 assessment 之间因路径表示不一致而破坏跨文件 identity
- [x] 在 replay harness 中校验 gate 对 assessment / continuous improvement / archive / feedback 的 artifact 引用与真实工件路径一一对应

### D82 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| quality_assessment metadata | `report_metadata.output_path` 统一斜杠规范化，便于与 gate artifact 引用做稳定比对 | 不新增字段、不改变合同版本 |
| gate -> downstream identity | 在 `tests/unit/test_inventory_signal_quality_gate_replay.py` 中新增 `_assert_gate_artifact_identity_isomorphic(...)`，将 gate artifact 引用与 assessment / continuous / archive / feedback 的 `report_metadata` 路径逐项对齐 | 不改动 gate `results[*].details` 的既有字段名 |
| replay coverage | stable / regressing / uncategorized_regressing / improving-target-change / improving-target-cleared 五类回放样本复用同一套 identity 断言 | 不改变 quiet/loud 语义断言 |

### D82 验证结论

- [x] `tests/unit/test_quality_assessment.py` 已新增断言，验证导出后的 `report_metadata.output_path` 使用统一斜杠表示。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已扩展为同时校验 gate artifact 引用与 assessment / continuous improvement / archive / feedback 真实工件路径完全同构。
- [x] 新增 identity 护栏在 stable、regressing、uncategorized regressing、improving-target-change、improving-target-cleared 五类回放样本上复用，确保不是单一路径偶然成立。

## 79. D83 Export Phase 明细与 Report Metadata 路径同构护栏

- [x] 将治理模块 `metadata.phase_history` 中 export phase 的路径明细统一规范化到与 `report_metadata` 相同的斜杠表示
- [x] 把“export phase details 与 report_metadata 路径一一对应”提升为模块级导出测试与主链 replay harness 的共同护栏
- [x] 保持既有字段名不变，仅统一路径表示和同构断言，不改动 loud/quiet 语义

### D83 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| quality_assessment / continuous_improvement / archive / feedback / gate 导出相位 | export phase details 中的 `output_path`、`history_path`、`latest_output`、`dossier_path`、`markdown_path`、`issue_dir`、`issue_index` 统一使用规范化斜杠路径 | 不新增字段、不改动相位名 |
| 模块级导出测试 | 在对应 `tests/unit/test_quality_*.py` 中新增断言，验证 `phase_history[-1].details` 与 `report_metadata` 同构 | 不改变既有 contract_version 与 artifact_reference 断言 |
| replay harness | 在 `tests/unit/test_inventory_signal_quality_gate_replay.py` 中新增 `_assert_export_phase_details_isomorphic(...)`，统一校验 assessment / continuous / archive / feedback / gate 五模块导出明细与 report_metadata 路径同构 | 不影响现有 issue draft / runner alert / inventory 语义断言 |

### D83 验证结论

- [x] `tests/unit/test_quality_assessment.py`、`tests/unit/test_continuous_improvement_loop.py`、`tests/unit/test_quality_improvement_archive.py`、`tests/unit/test_quality_feedback.py`、`tests/unit/test_quality_gate.py` 已新增导出相位明细与 `report_metadata` 的同构断言。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已在 stable、regressing、uncategorized regressing、improving-target-change、improving-target-cleared 五类主链回放中统一复用 export phase 同构护栏。
- [x] 新增护栏修复的是路径表示漂移的根因，而非在测试侧放宽比较规则；真实工件导出路径现在在 `phase_history` 与 `report_metadata` 两侧保持同一文本表示。

## 80. D84 人读工件正文路径引用同构护栏

- [x] 将 `report_metadata` 中的关键工件路径显式下沉到 feedback Markdown 与 archive dossier，避免人审时只能回看 JSON 才能定位导出物
- [x] 把“正文路径文本 = report_metadata 路径”纳入模块级单测与 replay harness，形成 JSON / Markdown / dossier 三侧同构护栏
- [x] 保持既有正文语义与 quiet/loud 分流不变，仅新增 Artifact References 区块

### D84 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| feedback Markdown | 新增 `Artifact References` 区块，显式列出 feedback JSON、Markdown、issue index、issue dir 与 issue draft files | 不改动既有 inventory / priority actions / owner notifications 正文 |
| archive dossier | 新增 `Artifact References` 区块，显式列出 history、latest output、dossier 三条路径 | 不改动既有 snapshot / risks / inventory trend 正文 |
| 模块级单测 | `tests/unit/test_quality_feedback.py` 与 `tests/unit/test_quality_improvement_archive.py` 新增正文路径文本断言 | 不改变既有排序与语义断言 |
| replay harness | `tests/unit/test_inventory_signal_quality_gate_replay.py` 新增 `_assert_human_readable_artifact_references_isomorphic(...)`，统一校验人读工件正文里的路径文本与 `report_metadata` 同构 | 不改动 loud/quiet 行为判定 |

### D84 验证结论

- [x] `tests/unit/test_quality_feedback.py` 已验证反馈 Markdown 中的 artifact references 与 `report_metadata.output_path / markdown_path / issue_index_path / issue_dir / issue_draft_files` 完全一致。
- [x] `tests/unit/test_quality_improvement_archive.py` 已验证 archive dossier 中的 artifact references 与 `report_metadata.history_path / latest_output_path / dossier_path` 完全一致。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已在 stable、regressing、uncategorized regressing、improving-target-change、improving-target-cleared 五类回放样本上复用正文路径同构护栏，确保不是单场景偶然成立。

## 81. D85 Issue Index / Issue Draft 路径自描述与同构护栏

- [x] 为 issue index JSON 增加顶层 `report_metadata` 路径摘要，避免下游只能从 feedback JSON 反推 issue index 自身位置与草稿集合
- [x] 为 issue draft Markdown 正文增加 `Artifact References` 区块，显式列出 issue index、issue directory、issue draft file 与 index position
- [x] 将 issue index 顶层元数据、issue draft 正文路径文本与 feedback `report_metadata.issue_draft_*` 一起纳入 replay harness 同构护栏

### D85 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| issue index JSON | 新增顶层 `report_metadata.issue_index_path / issue_dir / issue_files / issue_owners / issue_titles` | 不改动既有 `count` 与 `items` 结构 |
| issue draft Markdown | 新增 `Artifact References` 区块，显式列出 issue index、issue directory、issue draft file、index position | 不改动既有 summary / inventory trend / action items / acceptance 正文 |
| 模块级单测 | `tests/unit/test_quality_feedback.py` 新增 issue index 顶层元数据与 issue draft 正文路径文本断言 | 不改变既有 owner 排序与语义断言 |
| replay harness | `tests/unit/test_inventory_signal_quality_gate_replay.py` 新增 issue index 顶层元数据与 issue draft 正文 artifact references 同构断言 | 不改变 quiet/loud 行为与 runner alert 断言 |

### D85 验证结论

- [x] `tests/unit/test_quality_feedback.py` 已验证 issue index 顶层 `report_metadata` 与 feedback `report_metadata.issue_draft_*` 完全同构，并验证 issue draft 正文里的 artifact references 与实际文件路径一致。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已在 stable、regressing、uncategorized regressing、improving-target-change、improving-target-cleared 五类回放样本上复用 issue index / issue draft 路径同构护栏。
- [x] 新增护栏把 issue index / issue draft 从“被引用对象”升级为“自描述对象”，后续人工复核或下游消费无需再强依赖 feedback JSON 反推这些路径。

## 82. D86 Issue 身份字段全文同构护栏

- [x] 将 `template`、`labels`、`index_position` 从零散字段提升为 feedback `report_metadata`、issue index 顶层 `report_metadata`、issue index `items` 与 issue draft 正文四侧共享身份字段
- [x] 让 issue draft Markdown 的 `Artifact References` 不只描述路径，还显式描述 template、labels、index position，避免人工复核时仍需回跳 JSON 取身份元数据
- [x] 把 issue index / issue draft / feedback JSON 的全文 identity 比对纳入模块级单测与 replay harness

### D86 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| feedback report_metadata | 新增 `issue_draft_templates`、`issue_draft_labels`、`issue_draft_index_positions` | 不改动既有 `issue_draft_owners / titles / files` 字段名 |
| issue index JSON | `items[*]` 新增 `index_position`，顶层 `report_metadata` 新增 `issue_templates`、`issue_labels`、`issue_index_positions` | 不改动既有 `count` 与 item 核心字段 |
| issue draft Markdown | `Artifact References` 区块新增 template、labels、index position 的正文自描述 | 不改动既有 summary / action items / acceptance 正文 |
| 单测与 replay harness | 模块级与主链回放统一校验 owner/title/file/template/labels/index_position 六类身份字段全文同构 | 不改变 quiet/loud 语义断言 |

### D86 验证结论

- [x] `tests/unit/test_quality_feedback.py` 已验证 feedback `report_metadata.issue_draft_*` 与 issue index 顶层 `report_metadata` 以及 `items[*]` 在 owner/title/file/template/labels/index_position 上完全同构。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已在 stable、regressing、uncategorized regressing、improving-target-change、improving-target-cleared 五类回放样本上复用 issue 身份字段全文同构护栏。
- [x] issue draft Markdown 现在已能独立表达路径与身份字段，后续人工排障不需要再从 feedback JSON 反查 template、labels 或索引位置。

## 83. D87 Issue Summary / Inventory Trend 正文语义同构护栏

- [x] 将 issue draft 正文 `Summary` 中的 `quality_score`、`trend_status` 以及 `Inventory Trend` 中的历史趋势字段提升为 feedback `report_metadata`、issue index 顶层 `report_metadata`、issue index `items[*]` 与 issue draft 正文四侧共享语义字段
- [x] 保持既有 issue draft Markdown 模板不变，只新增结构化镜像字段，避免为了可校验性反向扰动人工阅读模板
- [x] 将 issue draft 正文 `Summary` / `Inventory Trend` 文本与 JSON 元数据的反向恢复比对纳入模块级单测与 replay harness

### D87 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| feedback report_metadata | 新增 `issue_draft_quality_scores`、`issue_draft_trend_statuses`、`issue_draft_inventory_*` 派生列表 | 不改动既有 `issue_draft_owners / titles / files / templates / labels / index_positions` 字段名 |
| issue index JSON | `items[*]` 新增 `quality_score`、`trend_status`、`inventory_trend_status`、`inventory_*` 语义字段；顶层 `report_metadata` 新增对应列表 | 不改动既有 `count`、`items[*].owner/title/file/template/labels/index_position` |
| issue draft Markdown | 继续沿用既有 `Summary` 与 `Inventory Trend` 正文模板，由回放护栏锁定这些正文文本与 JSON 语义字段同构 | 不改动既有 action items / acceptance / artifact references 模板 |
| 单测与 replay harness | 模块级与主链回放统一校验 quality score、trend status、inventory trend status/history/delta/target 的全文同构 | 不改变 quiet/loud 语义断言 |

### D87 验证结论

- [x] `tests/unit/test_quality_feedback.py` 已验证 feedback `report_metadata.issue_draft_*` 与 issue index 顶层 `report_metadata`、`items[*]` 在 Summary / Inventory Trend 语义字段上完全同构。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已在五类回放样本上复用 issue draft 正文 Summary / Inventory Trend 文本与 JSON 语义字段的反向恢复护栏。
- [x] issue draft 现在既能自描述路径与身份字段，也能自描述质量分数、趋势状态与 inventory 回退细节；人工排障与下游自动化都不必再从 feedback 总报告重新拼接这些语义。

## 84. D88 Issue Action / Acceptance 结构化镜像与 Residual-Risk Recovery 三层样本

- [x] 将 issue draft 正文 `Action Items` 与 `Acceptance` 提升为结构化字段，写入 feedback `report_metadata`、issue index 顶层 `report_metadata`、issue index `items[*]` 与导出的 `issue_drafts[*]`
- [x] 保持既有 issue draft Markdown 模板不变，由模块级单测与 replay harness 反向校验正文 action/acceptance 文本与 JSON 结构化字段同构
- [x] 新增一类 `inventory_trend = improving` 但 `missing_contract_count = 1` 的 residual-risk recovery 样本，并补齐真实受控样本、end-to-end、replay harness 三层一致性

### D88 回放资产范围

| 范围 | 新增验证/护栏 | 保持兼容 |
| --- | --- | --- |
| feedback report_metadata | 新增 `issue_draft_action_items`、`issue_draft_acceptance_checks` 派生列表 | 不改动既有 issue draft 身份字段与 Summary / Inventory Trend 字段名 |
| issue index JSON | `items[*]` 新增 `action_items`、`acceptance_checks`；顶层 `report_metadata` 新增 `issue_action_items`、`issue_acceptance_checks` | 不改动既有 `count`、`items[*].owner/title/file/template/labels/index_position` |
| issue draft Markdown | 继续沿用既有 `Action Items` / `Acceptance` 正文模板，由护栏校验正文文本与结构化字段同构 | 不改动既有章节名、勾选文案与 artifact references 模板 |
| end-to-end / replay harness | 新增 `improving + residual missing contract` 样本：feedback 因 snapshot 缺口继续产生 `quality-governance` issue draft，但 stage1/stage2 因 trend 非 regressing 继续保持 quiet | 不改动既有 stable / regressing / improving-target-change / target-cleared 语义 |
| real workspace controlled sample | 在当前仓库临时注入 `tools/inventory_probe_residual_missing_consumer.py` 生成真实 inventory 缺口，再受控改写 archive latest 为 `improving` 残余风险态，验证后删除样本并重跑 stable 主链恢复 | 不改动生产 inventory 扫描或 runner 告警规则 |

### D88 验证结论

- [x] `tests/unit/test_quality_feedback.py` 已验证 feedback `report_metadata.issue_draft_action_items / issue_draft_acceptance_checks` 与 issue index 顶层 `report_metadata`、`items[*]` 和导出 `issue_drafts[*]` 完全同构，并验证正文 `Action Items` / `Acceptance` 文本可从结构化字段反向恢复。
- [x] `tests/unit/test_inventory_signal_end_to_end.py` 已新增 improving residual-risk 样本，验证 `inventory_trend.status = improving` 且 `missing_contract_count = 1` 时，feedback 保持 loud，但 stage1/stage2 dry-run 仍无 `governance_alerts`。
- [x] `tests/unit/test_inventory_signal_quality_gate_replay.py` 已新增 improving residual-risk 九端回放，验证 inventory / improvement / archive / dossier / feedback / issue index / issue draft / stage1 / stage2 在该语义下保持一致。
- [x] 真实仓库受控样本已验证：临时 missing consumer 使 `quality_consumer_inventory.missing_contract_count = 1`，受控 latest 使 `inventory_trend.status = improving`、`missing_contract_delta = -1`，`output/quality-feedback.json` 扩展为 `module-owners + quality-governance` 双 owner，stage1/stage2 全局 dry-run 报告仍无 `governance_alerts`；随后已删除样本并重跑 `tools/quality_gate.py` 恢复 stable 基线。

## 51. D55 Stage1 Runner 编排档案合同补齐

- [ ] 在不改变 `-Day`、`-All`、`-DryRun` 等既有 CLI 语义的前提下，给 stage1 runner 的 day/global JSON 报告补齐统一治理合同
- [ ] 保留原有 step 级执行结果、pass rate、rollback tips、strict rollback flow 字段，避免影响既有消费方
- [ ] 用单个导出入口统一写 day report 与 global report，保证 `last_completed_phase` 与真实写盘阶段一致

### D55 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| day report | 增加 `metadata`、`report_metadata`、`analysis_summary`、`failed_operations` | 原有 `day`、`steps`、`pass_rate_percent`、`rollback_tips`、`strict_rollback_flow` 不变 |
| global report | 增加统一治理合同与全局执行摘要 | 原有 `days` 列表和全局退出码语义不变 |
| 配置 | 新增 `governance.stage1_runner.export_contract_version = d55.v1` | 不影响其他治理模块配置 |

### D55 统一字段口径

| 字段 | day report | global report |
| --- | --- | --- |
| `metadata` | `execute_stage1_day`、`assemble_stage1_day_summary`、`export_stage1_day_summary` | `run_stage1_days`、`assemble_stage1_global_summary`、`export_stage1_global_summary` |
| `report_metadata` | `result_schema = stage1_day_execution_report` | `result_schema = stage1_global_execution_report` |
| `analysis_summary` | step 类型分布、rollback 压力、pass rate band | day 数、失败日数、阈值中断数、平均通过率 |
| `failed_operations` | 记录失败 step 与阈值跌破事件 | 聚合失败 day 与对应报告位置 |

### D55 验证要求

- [ ] dry-run 下 day report 的 `last_completed_phase` 必须为 `export_stage1_day_summary`
- [ ] dry-run 下 global report 的 `last_completed_phase` 必须为 `export_stage1_global_summary`
- [ ] D55 完成后重新跑 D54 inventory，下一跳候选应从 stage1 runner 前移到 stage2 runner

### D55 验证结论

- [ ] `tools/stage1_d1_d10_runner.ps1 -Day D1 -DryRun` 已生成带 `metadata`、`report_metadata`、`analysis_summary`、`failed_operations` 的 day/global 报告
- [ ] 最新 dry-run day report 的 `last_completed_phase = export_stage1_day_summary`，global report 的 `last_completed_phase = export_stage1_global_summary`
- [ ] `tests/unit/test_stage1_runner_contract.py` 与 `tests/unit/test_quality_consumer_inventory.py` 已通过
- [ ] 重新运行 D54 inventory 后，推荐下一跳已切换为 `tools/stage2_s2_1_s2_6_runner.ps1`
- [ ] quality_gate 仍保持绿色，`code_quality.warning_count = 44`

## 52. D56 Stage2 Runner 编排档案合同补齐

- [ ] 在不改动现有 stage 步骤顺序的前提下，为 stage2 runner 增加统一治理档案合同
- [ ] 保留原有 `.log` 执行日志，同时新增 stage/global JSON 报告，便于机器恢复和治理追踪
- [ ] 新增 `-DryRun` 仅作为附加能力，用于合同验证，不改变非 dry-run 的既有执行路径

### D56 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| stage report | 增加 `metadata`、`report_metadata`、`analysis_summary`、`failed_operations` | 原有 stage log 仍保留，步骤编排不变 |
| global report | 增加 `stage2_all_*.json` 汇总档案 | 不影响单 stage 的 stdout 和日志输出 |
| CLI | 增加 `-DryRun` 参数 | `-Stage`、`-All`、`-TargetCodeHealth` 语义不变 |

### D56 统一字段口径

| 字段 | stage report | global report |
| --- | --- | --- |
| `metadata` | `execute_stage2_stage`、`assemble_stage2_stage_summary`、`export_stage2_stage_summary` | `run_stage2_stages`、`assemble_stage2_global_summary`、`export_stage2_global_summary` |
| `report_metadata` | `result_schema = stage2_stage_execution_report` | `result_schema = stage2_global_execution_report` |
| `analysis_summary` | step 类型分布、pass rate band、dry-run 标记 | stage 数、失败 stage 数、平均通过率 |
| `failed_operations` | 记录失败 step 及命令退出信息 | 聚合失败 stage 与对应报告路径 |

### D56 验证要求

- [ ] `-Stage S2-1 -DryRun` 生成的 stage report 中 `last_completed_phase = export_stage2_stage_summary`
- [ ] `-All -DryRun` 生成的 global report 中 `last_completed_phase = export_stage2_global_summary`
- [ ] D56 完成后再次运行 inventory，应不再存在 runner 类缺口候选

### D56 验证结论

- [ ] `tools/stage2_s2_1_s2_6_runner.ps1 -Stage S2-1 -DryRun` 已生成带 `metadata`、`report_metadata`、`analysis_summary`、`failed_operations` 的 stage/global 报告
- [ ] 最新 stage report 的 `last_completed_phase = export_stage2_stage_summary`，global report 的 `last_completed_phase = export_stage2_global_summary`
- [ ] `tools/stage2_s2_1_s2_6_runner.ps1 -All -DryRun` 已覆盖 S2-1 到 S2-6，全局报告 `analysis_summary.stage_count = 6`，`failed_stage_count = 0`
- [ ] `tests/unit/test_stage2_runner_contract.py` 与 `tests/unit/test_quality_consumer_inventory.py` 已通过
- [ ] 重新运行 D54 inventory 后，`eligible_missing_contract_count = 0`，已不再推荐 runner 类下一跳候选
- [ ] quality_gate 仍保持绿色，`code_quality.warning_count = 44`

## 53. D57 Quality Gate 统一治理合同补齐

- [ ] 将 `tools/quality_gate.py` 自身纳入统一治理合同，而不是只要求其下游消费者输出合同字段
- [ ] 保持现有 quality gate CLI、stdout 摘要和下游驱动顺序不变，仅补齐运行态 metadata 与导出合同
- [ ] 用单一 export 入口写出 `output/quality-gate.json`，避免最终写盘阶段与 `last_completed_phase` 脱节

### D57 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| quality gate report | 增加 `metadata`、`report_metadata`、`analysis_summary`、`failed_operations` | 原有 `overall_success`、`results` 结构保持不变 |
| 配置 | 新增 `governance.quality_gate.export_contract_version = d57.v1` | 不影响 D49-D56 已完成模块的配置语义 |
| 导出 | 新增 `export_quality_gate_report` 单入口 | `--report` 参数和既有输出路径保持不变 |

### D57 统一字段口径

| 字段 | quality gate report |
| --- | --- |
| `metadata` | `run_logic_gate`、`run_dependency_graph_gate`、`run_code_quality_gate`、`run_unit_test_gate`、`run_quality_assessment_gate`、`run_continuous_improvement_gate`、`run_quality_improvement_archive_gate`、`run_quality_feedback_gate`、`assemble_quality_gate_report`、`export_quality_gate_report` |
| `report_metadata` | `result_schema = quality_gate_report` |
| `analysis_summary` | gate 总数、失败 gate 数、success rate、失败 gate 名单 |
| `failed_operations` | 记录失败 gate 或运行异常，并保留 gate metrics/details 上下文 |

### D57 验证结论

- [ ] `tools/quality_gate.py` 输出的 `output/quality-gate.json` 已包含 `metadata`、`report_metadata`、`analysis_summary`、`failed_operations`
- [ ] 最新质量门报告的 `report_metadata.contract_version = d57.v1`，`last_completed_phase = export_quality_gate_report`
- [ ] `tests/unit/test_quality_gate.py` 已补充 quality gate 自身合同字段与导出阶段断言，并与 `tests/unit/test_quality_consumer_inventory.py` 一起通过
- [ ] 重新运行 inventory 后，`missing_contract_count = 0`，`tools/quality_gate.py` 已不再被识别为 remaining missing_contract out_of_scope 模块
- [ ] 真实质量门回归仍保持绿色，`overall_success = true`，`code_quality.warning_count = 44`

## 54. D58 Cycle Demo 聚合档案合同补齐

- [ ] 将 [run_cycle_demo.py](run_cycle_demo.py) 作为非 runner 的聚合消费者纳入统一治理合同，补齐 iteration 汇总、cycle 汇总与最终写盘的治理字段
- [ ] 保留现有 demo CLI、模块执行路径与输出摘要，仅在汇总层和导出层补充 `metadata`、`report_metadata`、`analysis_summary`、`failed_operations`
- [ ] 新增单一 `export_cycle_demo_report` 写盘入口，保证 cycle 结果的 `last_completed_phase` 与最终落盘一致

### D58 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| iteration summary | 增加 iteration 级 `metadata`、`analysis_summary`、`failed_operations` | 原有 `modules`、`quality_metrics`、`academic_insights`、`recommendations` 不变 |
| cycle report | 增加顶层统一治理合同与导出元数据 | 原有 `iterations`、`performance_metrics`、`academic_analysis` 结构保持不变 |
| 配置 | 新增 `governance.cycle_demo.export_contract_version = d58.v1` | 不影响其他治理模块配置 |

### D58 统一字段口径

| 字段 | cycle demo |
| --- | --- |
| `metadata` | `initialize_cycle_demo_modules`、`run_cycle_demo_iterations`、`assemble_cycle_demo_summary`、`export_cycle_demo_report` |
| `report_metadata` | `result_schema = cycle_demo_report` |
| `analysis_summary` | iteration 数、成功/失败 iteration 数、平均执行时间、overall quality score |
| `failed_operations` | 记录 iteration 失败与 demo 聚合阶段异常 |

### D58 验证结论

- 静态检查已通过，`run_cycle_demo.py` 与 `tests/unit/test_cycle_demo_contract.py` 无新增错误。
- `tests/unit/test_cycle_demo_contract.py` 已通过，覆盖 iteration 汇总合同与顶层导出合同，验证 `report_metadata.contract_version = d58.v1`。
- 最小化 demo 导出验证已通过，输出文件的 `metadata.last_completed_phase = export_cycle_demo_report`，且保留原有 iteration 汇总与摘要输出行为。

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

## 23. D27 理论框架二次治理补充检查项

本章节用于 D27 类 theoretical framework 二次治理对齐，强调研究框架编排轨迹、失败操作结构、导出版本刷新与 cleanup 重置一致性。

### 23.1 理论框架契约一致性

- [ ] 研究摘要输出 `analysis_summary` 与 `final_status`
- [ ] 失败操作以稳定 `failed_operations` 列表输出，字段使用 `operation`
- [ ] 导出结果与研究摘要输出统一 `report_metadata`

### 23.2 研究编排可观测性

- [ ] 假设生成、实验设计、洞察生成、假设验证、知识图谱构建、导出记录 `phase_history`
- [ ] 阶段异常写入 `failed_phase`
- [ ] 成功路径刷新 `completed_phases` 与 `last_completed_phase`

### 23.3 导出与清理安全

- [ ] 导出不会暴露枚举、dataclass 或 callable 原始对象
- [ ] 导出文件可被 `json.load` 直接回读
- [ ] cleanup 后运行态元数据与研究缓存重置为稳定空状态

## 24. D28 系统级迭代二次治理补充检查项

本章节用于 D28 类 system iteration 二次治理对齐，强调系统级失败操作、系统摘要契约、导出版本刷新与 cleanup 重置一致性。

### 24.1 系统级迭代契约一致性

- [ ] 系统性能报告输出 `analysis_summary` 与 `final_status`
- [ ] 失败操作以稳定 `failed_operations` 列表输出，字段使用 `operation`
- [ ] 导出结果与系统报告输出统一 `report_metadata`

### 24.2 系统编排可观测性

- [ ] 系统迭代执行、导出记录系统级 `phase_history`
- [ ] 阶段异常写入系统级 `failed_phase`
- [ ] 成功路径刷新 `completed_phases` 与 `last_completed_phase`

### 24.3 导出与清理安全

- [ ] 导出不会暴露枚举、dataclass 或 callable 原始对象
- [ ] 导出文件可被 `json.load` 直接回读
- [ ] cleanup 后运行态元数据、失败操作与系统缓存重置为稳定空状态
