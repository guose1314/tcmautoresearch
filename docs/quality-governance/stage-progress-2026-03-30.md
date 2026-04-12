# 阶段性摘要（2026-03-30）

## 1. 当前落点

- 当前分支：stage2-s2_1-preprocessor-opt
- 当前基线 HEAD：e777eb5（stage1 D28 system iteration refresh）
- 当前阶段治理范围：D29-D99 持续推进，多数改动集中在统一治理合同、质量链三档案、stage runner 合同、inventory 扫描扩围、AutoResearch runner 治理与 issue 合同连续收缩。
- 当前语义基线保持不变：当 `inventory_trend = regressing` 时，feedback 与 stage runners 同时 loud；当 `inventory_trend = improving/stable` 但 residual risk 尚未清零时，feedback 仍可继续 loud 并保留 issue/action 线索，而 stage1/stage2 runners 保持 quiet。
- 当前分支名已经落后于实际工作范围；本轮实际推进已覆盖 D29-D62，多数改动集中在统一治理合同、质量链三档案、stage runner 合同、inventory 扫描扩围与 AutoResearch runner 治理。

## 1.1 快速续接卡

- 权威台账：`docs/quality-governance/refactor-quality-templates.md`，当前已记录到 D99。
- 阶段摘要：`docs/quality-governance/stage-progress-2026-03-30.md`，用于快速恢复上下文。
- 当前稳定态：`output/quality-feedback.json` 中 `report_metadata.contract_version = d77.v1`；公开 JSON 不再包含 `issue_drafts`、`issue_index_payload` 与 `analysis_summary.issue_draft_count`；`output/quality-feedback-issues.json` 仅含 `count` 与 `items`，不再有 `report_metadata`。
- 当前稳定态：最新 stage1/stage2 全局 dry-run 报告不包含 `governance_alerts`。
- 最新实测基线：定向治理测试已通过 `114 passed, 0 failed`；真实命令 `c:/Users/hgk/tcmautoresearch/venv/Scripts/python.exe tools/quality_gate.py --report output/quality-gate.json` 已成功执行，`overall_success = True`、`quality_feedback.success = True`。
- 关键验证入口：`tests/unit/test_inventory_signal_quality_gate_replay.py` 负责九端一致性并已覆盖 improving recovery、mixed residual-risk recovery、target-cleared recovery quiet replay，现也负责 gate / assessment / continuous improvement / archive / feedback 之间的 artifact 路径同构护栏、export phase details 与 `report_metadata` 路径同构护栏、feedback Markdown / archive dossier 正文路径文本护栏，以及 issue index / issue draft 的 `issue_body` 单对象可逆恢复护栏；`tests/unit/test_inventory_signal_end_to_end.py` 负责 feedback 与 runner 的 quiet/loud 联动；`tests/unit/test_quality_feedback.py` 负责 feedback JSON / Markdown / issue draft / issue index 的 `issue_body`、artifact references 与公开合同收缩护栏；`tests/unit/test_quality_assessment.py`、`tests/unit/test_continuous_improvement_loop.py`、`tests/unit/test_quality_improvement_archive.py`、`tests/unit/test_quality_gate.py` 继续承担模块级稳定列表与导出相位路径护栏。
- 继续推进前的最小复核顺序：先看台账 D89-D99，再读 latest 工件，再跑定向治理测试，最后视需要补真实仓库可控样本回放。
- 下一个自然续接点：D99 已移除 issue index 的 `report_metadata` 自引用块；若继续做 D100，更自然的方向将转向 feedback `report_metadata.issue_dir` 导航镜像清理（可由 `issue_index_path` 推导），或补更细粒度的 residual-risk / recommended_next_target / 多 owner 分支。

## 1.2 本阶段收口摘要

- 已完成 D89-D99 一条连续收缩线，核心目标是把 quality_feedback 的 issue 语义收敛到独立 issue index 文件中的单一 `issue_body` 事实源，并逐层删除公开兼容字段、内部投影层、report_metadata 镜像列表、issue body 批量镜像数组、feedback JSON 内嵌的整块 issue index 载荷、feedback JSON 顶层公开 issue 列表、最后一个公开 issue 批量派生计数镜像，以及 issue index 的 `report_metadata` 自引用块。
- 当前对外最小事实面已经稳定：公开消费者若需要批量 issue，只应读取 `report_metadata.issue_index_path` 指向的独立文件；若需要 owner、title、labels、template、issue 文件、排序位置，只应从 `output/quality-feedback-issues.json.items[*].issue_body.summary` 与 `issue_body.artifact_references` 读取，而不应再依赖 feedback JSON 中的任何 issue 镜像。
- 当前验证闭环已经稳定覆盖模块级单测、end-to-end、quality_gate replay harness 与真实仓库 quality_gate 回放，因此后续任意一天续接时，可以直接把 D95 视为新的公开合同基线，而不必再回溯旧平铺字段。
- 当前最重要的历史语义不要回退：improving / stable 场景下即使 feedback 继续 loud，也不能让 stage1/stage2 runners 误抬升 `governance_alerts`；只有 `inventory_trend.status = regressing` 才允许 runner 进入 loud 分支。

## 2. 本轮已完成的主线

### 2.1 统一治理合同补齐

- Core / Cycle / Research / Test 侧多模块已统一补齐 metadata、report_metadata、analysis_summary、failed_operations。
- cleanup 语义已向 cleaned 收敛，避免残留 terminated / terminated-like 语义。
- 失败路径 failed_operations 已普遍补 details、duration_seconds、last_completed_phase 等稳定字段。

涉及的关键模块包括：

- src/core/architecture.py
- src/core/module_base.py
- src/core/module_interface.py
- src/core/algorithm_optimizer.py
- src/cycle/ 旧 iteration 子系统（已于 2026-04-12 清理）
- src/research/research_pipeline.py
- src/research/theoretical_framework.py
- src/test/automated_tester.py
- src/test/integration_tester.py

### 2.2 质量治理主链补齐

- tools/quality_gate.py 已升级为统一治理入口，输出完整治理合同。
- tools/quality_assessment.py、tools/continuous_improvement_loop.py、tools/quality_improvement_archive.py、tools/quality_feedback.py 已全部接入统一治理合同。
- 质量主链已形成 JSON + Markdown + JSONL 的多档案闭环，且 export 阶段会稳定回填 last_completed_phase。

当前主链版本对齐：

- quality_gate: d63.v1
- quality_assessment: d49.v1
- continuous_improvement: d66.v1
- quality_improvement_archive: d65.v1
- quality_feedback: d77.v1
- quality_consumer_inventory: d62.v1

本轮新增的主链桥接点：

- quality_gate 已把 quality_consumer_inventory 作为正式 gate 执行并写入总报告。
- quality_feedback 已新增 inventory_summary，并会把 inventory 缺口或未归类观测转为优先行动。
- quality_feedback 已收缩公开 issue 合同，外部输出改为保留身份字段与 issue_body，删除由 issue_body 可逆恢复的平铺语义字段。
- quality_feedback 已进一步移除公开 issue_drafts 中的 output_file 写盘细节，并删除内部 issue 平铺兼容投影层，改为直接由 issue_body.artifact_references 汇总身份与路径元数据。
- quality_feedback 已删除 feedback / issue index report_metadata 中的 issue 引用影子列表，改为仅保留 issue_draft_bodies / issue_bodies，并从 artifact_references 反推总报告中的 issue draft 文件清单。
- quality_feedback 已进一步删除公开 issue_drafts 与 issue index items 的顶层身份/路径兼容字段，外部消费者统一改由 issue_body.summary 与 issue_body.artifact_references 读取公开语义。
- quality_feedback 已进一步删除 feedback / issue index report_metadata 中最后一层 issue body 批量影子数组，改为直接以公开 issue_drafts / issue_index_payload.items 作为唯一 issue body 列表事实源。
- quality_feedback 已进一步删除 feedback JSON 内嵌的 `issue_index_payload` 整块镜像，公开 issue index 统一只通过 `report_metadata.issue_index_path` 指向独立文件。
- quality_feedback 已进一步删除 feedback JSON 顶层 `issue_drafts` 列表，公开批量 issue 统一只通过独立 issue index 提供，feedback JSON 仅保留 issue draft 摘要计数与导航路径。
- quality_feedback 已进一步删除 feedback JSON `analysis_summary.issue_draft_count` 派生计数镜像，quality_gate 与 CLI 统一改为直接从独立 issue index 的 `count` 字段读取计数。
- quality_improvement_archive 已新增 inventory_summary，并在 dossier 中沉淀 Inventory Governance 区块。
- quality_improvement_archive 已新增 inventory_trend，并开始从 archive history 计算 inventory 历史变化。
- continuous_improvement 已新增 inventory_focus，并会把 archive history 中的 inventory_trend 转成后续 action/target。
- quality_feedback 已新增 inventory_trend 视图，并会在当前快照仍健康但历史趋势回退时生成 inventory 趋势型 follow-up 与 issue draft。
- 已新增 stable/regressing 双态端到端对照回归，统一验证 feedback 与 stage runner 的治理信号不会漂移。
- 已新增 quality_gate 全链真实回放测试，统一验证 inventory、continuous improvement、archive latest、archive dossier、feedback、feedback issue index、feedback issue draft body、stage1 runner、stage2 runner 九端一致性。
- regressing 回放下已额外细粒度锁定 `module-owners` issue draft 正文结构，避免非治理 owner 的 Markdown 模板在后续演进中发生静默漂移。
- 已新增 `uncategorized_root_script` 的第二条 regressing 回放路径，并对比 `missing_contract` / `uncategorized_root_script` 两条路径下 `module-owners` 与 `quality-governance` 正文差异，防止九端一致但语义分流错误。
- 已把 `feedback Markdown` 总报告也纳入两条 regressing 路径的差异断言，并完成一次真实仓库 uncategorized 可控样本回放，确认该路径不只在临时工作区成立。
- 已补一组真实仓库 trend-only 可控样本，通过受控 latest 注入验证 `inventory_summary = healthy` 且 `inventory_trend = regressing` 时的真实反馈/runner 分流。
- 已锁定 feedback JSON 与 feedback Markdown 的 owner 级 action 顺序，并在 Markdown 中展开 owner todo 明细以降低人审噪音。
- 已补一组 stable-target-change 抑噪样本，验证 `recommended_next_target_changed = true` 且 `inventory_trend = stable` 时不会误抬升治理提示。
- 已将 issue draft Markdown 的 action 顺序显式锁键，与 feedback JSON / feedback Markdown 一起形成完整的人审顺序护栏。
- 已将 `quality-feedback-issues.json.items` 的顺序也显式锁键，使 issue index 与 feedback JSON / feedback Markdown / issue draft Markdown 三端完全同构。
- 已补一组 improving-target-change 恢复态静默样本，验证 `inventory_trend = improving` 且 `recommended_next_target_changed = true` 时，反馈与 runner 仍不会误抬升治理提示。
- 已将 improving recovery quiet 语义并入 `quality_gate` replay harness，使九端真实回放也显式覆盖恢复态静默分支。
- 已将 feedback JSON 的 `issue_drafts` 升级为带真实 `file` 与 `index_position` 的派生索引，并由 issue index 反向校准顺序，形成跨文件引用护栏。
- 已将 `report_metadata.issue_draft_owners / issue_draft_titles / issue_draft_files` 纳入同构护栏，避免下游仅凭正文和 issue index 才能恢复稳定引用列表。
- 已补一组 improving-target-cleared 恢复态静默样本，验证推荐目标从 `tools/missing_consumer.py` 清空到 `none` 时，反馈与 runner 仍不会误抬升治理提示。
- 已将 `continuous_improvement`、`quality_improvement_archive`、`quality_gate` 的 `report_metadata` 也升级为输出稳定的 `artifact_reference_labels / artifact_reference_paths`，并让 `quality_gate` 额外导出 `gate_names`，把“派生引用列表锁顺序”从 feedback 扩展到更多治理模块。
- 已把 improving-target-cleared quiet recovery 补齐到 `tests/unit/test_inventory_signal_end_to_end.py`，使其与真实仓库受控样本、`tests/unit/test_inventory_signal_quality_gate_replay.py` 形成三层一一对应。
- 已把上述多模块 metadata 派生引用列表再推进到 `tests/unit/test_inventory_signal_quality_gate_replay.py` 的 stable / regressing / improving / target-cleared 主链回放断言中，避免只在模块级单测成立而在主链装配时漂移。
- 已把 gate artifact 引用进一步与 assessment / continuous improvement / archive / feedback 的真实 `report_metadata` 路径做跨文件同构护栏，并顺手统一了 `quality_assessment.report_metadata.output_path` 的路径表示。
- 已把 assessment / continuous improvement / archive / feedback / gate 的 export phase details 路径进一步统一到与 `report_metadata` 相同的文本表示，并在模块级单测与 replay harness 中双重锁定这种同构关系。
- 已把 feedback Markdown 与 archive dossier 的正文也显式输出 artifact references，并在模块级单测与 replay harness 中锁定正文路径文本与 `report_metadata` 的同构关系。
- 已把 issue index JSON 升级为自带顶层 `report_metadata` 路径摘要，并把 issue draft Markdown 的 Artifact References 也纳入同构护栏，避免下游再依赖 feedback JSON 反推这些文件关系。
- 已把 issue identity 的 template、labels、index_position 也纳入 feedback `report_metadata`、issue index 顶层元数据、issue index items 与 issue draft 正文四侧同构护栏，避免只锁路径而放过身份元数据漂移。
- 已把 issue draft 正文 `Summary` / `Inventory Trend` 中的 quality score、trend status、inventory trend status/history points/deltas/recommended next target 提升为 feedback `report_metadata`、issue index 顶层元数据与 issue index items 的稳定派生列表，并在模块级单测与 replay harness 中锁定这些正文语义的反向恢复一致性。
- 已把 issue draft 正文继续推进为单个 `issue_body` 对象，统一承载 `summary`、条件化 `inventory_trend`、`action_items`、`acceptance_checks`、`artifact_references`，并改由该对象单点渲染 issue draft Markdown，降低正文语义散落在多组字段中的回放成本。
- 已把 feedback `report_metadata.issue_draft_bodies`、issue index 顶层 `report_metadata.issue_bodies`、issue index `items[*].issue_body` 与导出 `issue_drafts[*].issue_body` 接通为同构护栏，模块级单测与 replay harness 现在优先校验这个单对象及其 Markdown 反向恢复。
- 已补一类 improving residual-risk 样本：`inventory_trend.status = improving` 但 `uncategorized_root_script` 当前仍为 1。当前该语义已在模块级单测、end-to-end、quality_gate replay harness 三层验证为“feedback 继续产生 quality-governance draft，stage1/stage2 runners 仍不抬升 governance_alerts”，且 issue draft 正文不会误带 `## Inventory Trend` 区块。
- 已把 issue index、feedback `report_metadata`、导出 `issue_drafts[*]` 中仍保留的平铺 issue 字段统一改为从 `issue_body.summary / inventory_context / action_items / acceptance_checks / artifact_references` 反向投影，确保正文语义与兼容字段共享单一事实源。
- 已在 `issue_body` 中补齐稳定的 `inventory_context`，使 improving / stable 等非 regressing 样本即便不渲染 `## Inventory Trend`，也能为兼容平铺字段与回放护栏提供统一来源。
- 已补一类 improving mixed residual-risk 样本：`missing_contract_count = 1` 且 `uncategorized_root_script = 1` 同时残留。当前该语义已在模块级单测、end-to-end、quality_gate replay harness 三层验证为“feedback 继续产生 quality-governance draft 且保留有序双 action，stage1/stage2 runners 仍不抬升 governance_alerts”。- 已移除 issue index (`quality-feedback-issues.json`) 的 `report_metadata` 自引用块，issue index 顶层缩减为 `{"count": N, "items": [...]}`。原 `report_metadata.issue_index_path`（自引用）与 `report_metadata.issue_dir`（与每条 item artifact_references 重复）均由 feedback `report_metadata` 和 per-item `artifact_references` 取代。跨文件同构护栏已从 issue index `report_metadata` 改为对比 item `artifact_references` 与 feedback `report_metadata`。
### 2.3 Stage runner 治理

- tools/stage1_d1_d10_runner.ps1 已扩展到 D67，并在 day/global 汇总中按需暴露 inventory 回退治理提示。
- tools/stage2_s2_1_s2_6_runner.ps1 已扩展到 D67，并在 stage/global 汇总中按需暴露 inventory 回退治理提示。
- 两个 runner 在 stable 或无 archive latest 场景下都不会输出 `governance_alerts`，只在 `inventory_trend.status = regressing` 时抬升治理噪音。
- 本轮真实修复了一个 Windows PowerShell 5.1 兼容性问题：`ConvertFrom-Json -Depth` 会导致 alert helper 静默回退为空，现已改为兼容调用。

对应版本：

- stage1_runner: d67.v1
- stage2_runner: d67.v1

### 2.4 聚合消费者 inventory 链

- tools/quality_consumer_inventory.py 已建立，并从仅扫描 tools 扩展到 tools + 根目录 orchestrator 脚本。
- inventory 已识别 cycle_demo_report、autorresearch_report 等新聚合档案。
- inventory 观测区已从单一 no_artifact_match 细化到分类化观测，generate_test_report.py 这类脚本会标记为“非治理域脚本”。

当前 inventory 实际状态：

- scanned_consumer_count = 9
- missing_contract_count = 0
- eligible_missing_contract_count = 0
- recommended_next_target = none
- root_script_observation_category_counts = { non_governance_domain_script: 1 }

主要输出：

- output/quality-consumer-inventory.json
- output/quality-consumer-inventory.md

### 2.5 Cycle demo 与 AutoResearch runner

- run_cycle_demo.py 已纳入统一治理合同，合同版本 d58.v1。
- tools/autorresearch/autorresearch_runner.py 已纳入统一治理合同，合同版本 d61.v1。
- AutoResearch runner 当前已覆盖：
  - baseline / iteration / assemble / export 相位跟踪
  - syntax_fail / crashed trial / improved_no_commit / improved_committed 落账
  - CLI 路径导出一致性
  - 真实 git 仓库下 improved_no_commit 与 improved_committed 两条分支的最小 smoke

## 3. 近期新增或关键测试

新增或显著扩展的测试包括：

- tests/unit/test_autorresearch_runner_contract.py
- tests/unit/test_cycle_demo_contract.py
- tests/unit/test_quality_consumer_inventory.py
- tests/unit/test_stage1_runner_contract.py
- tests/unit/test_stage2_runner_contract.py
- tests/unit/test_quality_gate.py
- tests/unit/test_quality_assessment.py
- tests/unit/test_continuous_improvement_loop.py
- tests/unit/test_quality_improvement_archive.py
- tests/unit/test_quality_feedback.py
- tests/unit/test_inventory_signal_end_to_end.py
- tests/unit/test_inventory_signal_quality_gate_replay.py
- tests/unit/test_architecture_cycle_quality.py
- tests/unit/test_automated_tester_quality.py
- tests/unit/test_integration_tester_quality.py
- tests/test_interface_consistency.py
- tests/test_research_pipeline_quality.py
- tests/test_theoretical_framework_quality.py

最近一轮明确执行并通过的验证：

- tests/unit/test_quality_feedback.py
- tests/unit/test_inventory_signal_end_to_end.py
- tests/unit/test_inventory_signal_quality_gate_replay.py
- 汇总结果：81 passed, 0 failed

## 4. 当前工作区范围

当前累计改动规模较大，git diff --stat 约为：

- 44 个已跟踪文件变更
- 8000+ 行新增
- 1300+ 行删除

此外还有新增文件尚在本轮范围内，包括：

- tools/quality_consumer_inventory.py
- tests/unit/test_autorresearch_runner_contract.py
- tests/unit/test_cycle_demo_contract.py
- tests/unit/test_quality_consumer_inventory.py
- tests/unit/test_stage1_runner_contract.py
- tests/unit/test_stage2_runner_contract.py
- 多个 docs/quality-archive/quality-improvement-*.md 档案快照

## 5. 后续接续建议

如果后面从任意一天恢复，建议按下面顺序接：

1. 先看 docs/quality-governance/refactor-quality-templates.md，那里已经记录到 D88，可直接在其后续节点继续排布。
2. 再看 output/quality-consumer-inventory.json、output/continuous-improvement.json、output/quality-improvement-archive-latest.json、output/quality-feedback.json、output/quality-feedback.md、output/quality-feedback-issues.json、output/quality-feedback-issues/*.md，以及最新 archive dossier 和 stage runner 生成的全局 JSON，确认 inventory summary、inventory trend、inventory targets、archive dossier、feedback issue index、feedback issue draft body、feedback markdown、runner governance_alerts 九端保持一致，且 `missing_contract` / `uncategorized_root_script` / trend-only / stable-target-change / improving-target-change / improving-target-cleared / improving-residual-missing-contract 七类语义不会串线，owner、issue draft、issue index、feedback JSON 内派生 `issue_drafts` 引用、feedback `report_metadata` 内 issue draft 派生引用列表、issue draft Summary / Inventory Trend / Action Items / Acceptance 正文语义，以及 `continuous_improvement` / `archive` / `gate` 的 `artifact_reference_*` 列表顺序也保持稳定。
3. 如果继续扩 inventory，优先处理 root_script_observations 中新增分类，而不是直接扩 artifact pattern。
4. 如果继续推进质量主链，优先复用 `tests/unit/test_inventory_signal_quality_gate_replay.py` 的 stable/regressing 双态样本，再跑 tools/quality_gate.py；若新增新的 inventory 回退类型，除临时工作区回放外也应补一次真实仓库可控样本回放，确认九端一致性与报告层语义都来自真实主链产物。
5. 如果继续推进 runner 或 feedback 治理，优先复用 `tests/unit/test_inventory_signal_end_to_end.py` 的 stable/regressing 双态样本，避免把常态噪音重新引入任一消费端。
6. 如果继续补 AutoResearch，优先加真实仓库下更贴近生产的 smoke，例如 improved_committed 后再触发 rollback / restore 的混合场景。

## 6. 风险与备注

- 当前分支名与实际工作主题不一致，后续如果继续长线推进，建议在下一个显式节点切到更贴近治理主题的分支名。
- docs/quality-archive 下已累计生成多份快照文档；如果后续继续频繁跑质量链，建议考虑按阶段整理或归档，避免噪音持续增大。
- 这份摘要只记录“现状”和“接续方式”，不替代详细治理台账；细节仍以 refactor-quality-templates.md 为准。
