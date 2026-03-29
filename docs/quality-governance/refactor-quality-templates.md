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

- [ ] 在不改变 `root_script_observations` 基本结构与 `no_artifact_match` 语义的前提下，给观测项增加分类层，避免后续根目录观测项增长后可读性快速下降
- [ ] 将 `generate_test_report.py` 一类脚本显式归入“非治理域脚本”，把“未命中治理档案模式”和“属于其他业务/验证域”区分开来
- [ ] 将 quality consumer inventory 合同版本提升到 `d62.v1`，以反映观测分类与摘要字段的新增

### D62 合同升级范围

| 范围 | 升级内容 | 保持兼容 |
| --- | --- | --- |
| observation payload | 新增 `observation_category`、`observation_category_label` | 原有 `observation_status = no_artifact_match` 保持不变 |
| analysis summary | 新增 `root_script_observation_category_counts` | 原有总数 `root_script_observation_count` 保持不变 |
| Markdown 报告 | 在 `Root Script Observations` 区块增加分类列与分类计数摘要 | 既有 Summary / Consumers / Recommendation 结构继续保留 |

### D62 验证结论

- [ ] `tests/unit/test_quality_consumer_inventory.py` 已通过，验证 `generate_test_report.py` 在观测区会被标记为 `non_governance_domain_script / 非治理域脚本`。
- [ ] 真实运行 inventory 后，Markdown 的 `Root Script Observations` 已展示分类列与分类计数，后续同类脚本可以按分类聚合阅读。
- [ ] `output/quality-consumer-inventory.json` 已升级到 `d62.v1`，并新增 `root_script_observation_category_counts` 字段。

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
