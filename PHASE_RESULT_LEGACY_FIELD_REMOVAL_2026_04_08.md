# PhaseResult 旧顶层字段删除清单（2026-04-08）

## 审计基线

- 运行样本：output/research_session_1775654329.json
- 运行命令：run_cycle_demo.py research 六阶段全流程
- 审计方法：
  - 先读取根 phase_results 下六个阶段的 metadata.deprecated_field_fallbacks
  - 再回读命中上下文，区分根阶段结果与 publish/report/cycle_snapshot 中的镜像快照
  - 最后交叉核对 src 下 helper 调用点与剩余直读点

结论：

- 根 phase_results 的真实 fallback 命中只有 2 项。
- 其余大量 deprecated_field_fallbacks 来自 research_artifact、report_session_result、cycle_snapshot 等嵌套镜像，不应重复计入删除决策。
- publish 根结果仍保留 output_files 顶层兼容字段，但本次真实运行未命中该 fallback；当前读取已优先走 artifacts。

## 可删除清单

### 第一批：暂不立刻删，但已进入删除准备态

这批字段已经定位到剩余命中入口，下一轮先迁移入口，再删除兼容字段。

1. experiment.selected_hypothesis

- 运行证据：根 phase_results.experiment.metadata.deprecated_field_fallbacks 命中 selected_hypothesis
- 直接原因：publish_phase 仍从 experiment_result 读取 get_phase_value(experiment_result, "selected_hypothesis", {})
- 当前标准承载位：results.selected_hypothesis
- 删除前动作：
  - 将 publish_phase 中对 selected_hypothesis 的消费改为优先使用 hypothesis 元信息或 experiment.results.selected_hypothesis 的标准路径
  - 补一条 publish 侧回归测试，确认 experiment 顶层 selected_hypothesis 缺失时仍能成功生成 publish 上下文

2. analyze.reasoning_results

- 运行证据：根 phase_results.analyze.metadata.deprecated_field_fallbacks 命中 reasoning_results
- 当前剩余入口：
  - generation/paper_writer.py
  - generation/output_formatter.py
  - research/phases/publish_phase.py
  - research/real_observe_smoke.py
- 当前标准承载位：results.reasoning_results
- 删除前动作：
  - 清掉以上模块对 analyze 顶层 reasoning_results 的最后兼容读取
  - 对 context 为 analysis PhaseResult、publish research_artifact、非 PhaseResult 普通 dict 三种输入分别补测试

### 第二批：可优先考虑删除顶层兼容输出，但需先清点持久化/快照依赖

1. publish.output_files

- 运行证据：本次根 publish 未产生 deprecated_field_fallbacks 命中 output_files
- 当前标准承载位：artifacts
- 仍需注意的非 helper 读取：
  - cycle/cycle_research_session.py 读取的是 report_export_result.get("output_files")，属于 report 导出结果，不是 PhaseResult 顶层兼容债务
  - publish_phase 内部对 paper_result/citation_result/report_generation_result 的 output_files 读取，属于子组件返回值，不是本轮 PhaseResult 删除目标
- 删除前动作：
  - 先确认对外 API/序列化是否仍显式依赖 publish 顶层 output_files
  - 确认 session 持久化或前端展示不把 output_files 作为硬编码字段展示

## 本轮不可纳入删除的字段

以下字段虽然仍出现在顶层输出或 grep 结果中，但不应在本轮 PhaseResult 兼容删除中处理：

1. observe.observations / observe.findings

- 本次运行根 observe 未命中 fallback
- 现有读取已大量迁移到 get_phase_value
- 可以保留到 selected_hypothesis 和 reasoning_results 清零后再统一删除

2. hypothesis.hypotheses

- 本次运行根 hypothesis 未命中 fallback
- 仍有很多代码出现 hypotheses，但多数是业务对象、提示词、引擎返回值，不等于 PhaseResult 兼容债务

3. publish.deliverables

- 本次运行根 publish 未命中 fallback
- deliverables 仍常用于摘要/展示层，建议与 output_files 一起作为 publish 批次处理

4. analyze.data_mining_result

- 本次运行根 analyze 未命中 fallback
- 当前 helper 读取已优先走 results.data_mining_result
- 仍有大量 research_artifact 普通 dict 读取，不能与顶层 PhaseResult 兼容路径混删

## 建议删除顺序

1. 先迁移 experiment.selected_hypothesis 的最后入口
2. 再迁移 analyze.reasoning_results 的最后入口
3. 运行六阶段真流程，要求根 phase_results.metadata.deprecated_field_fallbacks 为空
4. 删除 PhaseResult 输出中的对应顶层兼容字段
5. 最后处理 publish.output_files、publish.deliverables、observe/hypothesis 顶层镜像字段

## 删除完成判定

满足以下条件后，才适合真正移除旧顶层字段：

- 六阶段真实运行生成的根 phase_results 不再出现 deprecated_field_fallbacks
- tests/test_phase_result_contract.py 中标准契约路径测试保持通过
- publish/report/API 摘要链路不再依赖顶层散装字段
- session JSON 仍能被现有展示与摘要模块正常消费

## 当前结论

基于后续真实运行 output/research_session_1775658560.json，根 phase_results 已经搜不到 deprecated_field_fallbacks。

也就是说，上一版真实命中的两条兼容链已经被清空：

- experiment.selected_hypothesis
- analyze.reasoning_results

当前状态已经从“删除准备态”进入“已完成第一批旧顶层字段输出删除”的状态。

已完成：

- experiment 顶层 experiments / study_protocol / selected_hypothesis / success_rate 已移除，保留在 results 内。
- analyze 顶层 reasoning_results / data_mining_result 已移除，保留在 results 内。

运行验证：

- output/research_session_1775659862.json 中，experiment 与 analyze 根结果的 metadata 后已不再出现上述顶层字段。

已完成 publish 第一批：

- publish 顶层 deliverables 已移除，仅保留在 results.deliverables。
- publish 顶层 output_files 已移除，仅保留在 results.output_files 与 artifacts。

运行验证：

- output/research_session_1775660571.json 中，publish 根结果的 metadata 后仍保留 publications 等旧顶层字段，但已不再出现顶层 deliverables / output_files。

已完成 publish 第二批：

- publish 顶层 publications 已移除，仅保留在 results.publications。
- publish 顶层 citations 已移除，仅保留在 results.citations。

回归验证：

- tests/unit/test_publish_phase.py、tests/test_citation_manager.py、tests/test_phase_result_contract.py、tests/test_research_orchestrator.py 共 144 条定向测试通过。

运行验证：

- output/research_session_1775662087.json 中，publish 根结果的 results 内仍包含 publications / citations。
- 同一文件里，publish 根结果的 metadata 后已不再出现顶层 publications / citations；当前根级仅保留 bibtex / gbt7714 / formatted_references / paper_draft / imrd_reports / report_output_files / report_session_result / report_generation_errors / analysis_results / research_artifact / llm_analysis_context 等剩余兼容字段。

已完成 publish 第三批：

- publish 顶层 bibtex 已移除，仅保留在 results.bibtex。
- publish 顶层 gbt7714 已移除，仅保留在 results.gbt7714。
- publish 顶层 formatted_references 已移除，仅保留在 results.formatted_references。

回归验证：

- tests/unit/test_publish_phase.py、tests/test_citation_manager.py、tests/test_phase_result_contract.py、tests/test_research_orchestrator.py 共 144 条定向测试通过。

运行验证：

- output/research_session_1775662937.json 中，publish.results 已包含 bibtex / gbt7714 / formatted_references。
- 同一文件里，publish 根结果的 metadata 后已不再出现顶层 bibtex / gbt7714 / formatted_references；当前根级剩余兼容字段进一步收敛为 paper_draft / imrd_reports / report_output_files / report_session_result / report_generation_errors / analysis_results / research_artifact / llm_analysis_context 等。

下一步应继续处理 publish 剩余顶层镜像字段，而不是回到 experiment / analyze。

## 2026-04-12 publish 剩余根级字段分类审计

本轮只审计 publish 当前仍保留在根级的剩余字段，不直接改代码。

审计入口：

- producer 侧：src/research/phases/publish_phase.py 的 extra_fields
- 编排出口：src/orchestration/research_orchestrator.py
- 对外 DTO / dashboard：src/api/schemas.py、src/api/research_utils.py
- 真实回归与集成断言：tests/test_citation_manager.py、tests/unit/test_publish_phase.py、tests/test_rest_api.py、tests/test_web_console_api.py、tests/test_research_pipeline_quality.py

当前 publish 根级剩余字段：

- paper_draft
- paper_language
- imrd_reports
- report_output_files
- report_session_result
- report_generation_errors
- analysis_results
- research_artifact
- llm_analysis_context

### A. 应继续保留为根级字段

这批字段已经穿透到 orchestrator、REST/Web DTO、dashboard 和 smoke 摘要，不再只是 PhaseResult 兼容镜像，而是 publish 结果的对外高亮域对象。

1. analysis_results

- 证据：
  - src/api/schemas.py 的 ResearchResult DTO 直接暴露 analysis_results
  - src/orchestration/research_orchestrator.py 从 publish_result 提取 analysis_results 作为最终编排结果高亮
  - src/api/research_utils.py 的 dashboard/evidence board 直接消费 result.analysis_results
  - src/research/real_observe_smoke.py 直接消费 publish.analysis_results
- 结论：
  - 当前不应按“旧顶层兼容字段”直接删除
  - 它更接近 publish 专属外部 DTO，而不是通用 PhaseResult results 的重复镜像

2. research_artifact

- 证据：
  - src/api/schemas.py 的 ResearchResult DTO 直接暴露 research_artifact
  - src/orchestration/research_orchestrator.py 直接提取 publish_result.research_artifact
  - src/api/research_utils.py 的知识图谱与 evidence board 直接消费 result.research_artifact
  - tests/test_rest_api.py、tests/test_web_console_api.py、tests/test_research_pipeline_quality.py 均把它当作稳定输出域
- 结论：
  - 当前也不应并回通用 PhaseResult 根契约删除序列
  - 它与 analysis_results 一样，属于 publish 输出层的稳定对外对象

### B. 应并回标准契约或其标准承载位

这批字段要么已经在 results/artifacts 有标准承载位，要么只是 analysis_results / metadata 的重复展开。

1. paper_draft

- 现状：publish.results.paper_draft 已存在；根级 paper_draft 只是重复展开
- 剩余依赖：主要是 tests/test_citation_manager.py 与 tests/unit/test_publish_phase.py 的直接断言
- 结论：
  - 下一批可迁移测试与消费者到 results.paper_draft
  - 根级 paper_draft 应进入删除序列

2. imrd_reports

- 现状：publish.results.imrd_reports 已存在；根级 imrd_reports 只是重复展开
- 剩余依赖：以 tests/test_citation_manager.py 的直接断言为主
- 结论：
  - 下一批可并回 results.imrd_reports
  - 根级 imrd_reports 应进入删除序列

3. report_output_files

- 现状：PhaseResult artifacts 已能从 report_output_files 推导，phase_result._infer_artifacts 也已覆盖该字段
- 剩余依赖：主要是 tests/test_citation_manager.py 对 result["report_output_files"] 的直接断言
- 结论：
  - 对外标准承载位应优先是 artifacts
  - 如业务确实需要区分论文输出与 IMRD 输出，可显式迁入 results.report_output_files；否则直接依赖 artifacts 即可
  - 根级 report_output_files 不应长期保留

4. llm_analysis_context

- 现状：analysis_results.llm_analysis_context 已存在；根级 llm_analysis_context 是重复展开
- 剩余依赖：主要是 tests/test_citation_manager.py 对 result.llm_analysis_context 的直接断言
- 结论：
  - 标准读取位应收敛到 analysis_results.llm_analysis_context
  - 根级 llm_analysis_context 可进入删除序列

5. paper_language

- 现状：仅 producer 侧写入；src 与 tests 中未发现独立消费点
- 结论：
  - 不值得继续占用根级字段
  - 如仍需保留，建议迁入 metadata.paper_language；否则可直接删除

6. report_generation_errors

- 现状：producer 侧写入；metadata 已有 report_error_count，status 也会在出错时标记为 degraded
- 结论：
  - 根级 report_generation_errors 更像诊断明细，不适合作为稳定输出契约
  - 如要保留明细，建议迁入 metadata.report_generation_errors 或专门调试 artifact

7. report_session_result

- 现状：它是 ReportGenerator 的输入会话快照，producer 侧生成后又原样挂回根级
- 证据：src 中未发现该字段的独立消费者
- 结论：
  - 这不是标准 publish 输出 DTO，而是内部调试快照
  - 若无专门诊断需求，可直接移除；若需追溯，建议改为调试 artifact，而不是继续暴露在根级

### 审计结论

本轮分类后，publish 剩余根级字段可分为两类：

- 应继续保留：analysis_results、research_artifact
- 应进入下一批并回/删除序列：paper_draft、paper_language、imrd_reports、report_output_files、report_session_result、report_generation_errors、llm_analysis_context

也就是说，publish 根级后续真正需要保留的，很可能只剩下 analysis_results 与 research_artifact 两个 publish 专属外部 DTO。其余字段已经不再适合作为稳定根级契约继续存在。

### 建议下一批删除顺序

1. 先迁移 paper_draft、imrd_reports、llm_analysis_context 的测试与直读点
2. 再把 report_output_files 收敛到 artifacts 或 results.report_output_files
3. 然后删除无消费者的 paper_language、report_generation_errors、report_session_result 根级输出
4. 最后保留 analysis_results、research_artifact 作为 publish 输出层专属 DTO，不再混入“旧顶层兼容字段”删除序列

## 2026-04-12 publish 第四批根级镜像删除

已完成：

- publish 顶层 paper_draft 已移除，仅保留在 results.paper_draft。
- publish 顶层 imrd_reports 已移除，仅保留在 results.imrd_reports。
- publish 顶层 llm_analysis_context 已移除，标准读取位为 analysis_results.llm_analysis_context。

本轮未改动：

- paper_language
- report_output_files
- report_session_result
- report_generation_errors
- analysis_results
- research_artifact

回归验证：

- tests/unit/test_publish_phase.py
- tests/test_citation_manager.py
- tests/test_phase_result_contract.py

当前 publish 根级剩余字段进一步收敛为：paper_language、report_output_files、report_session_result、report_generation_errors、analysis_results、research_artifact。

下一步应优先处理 report_output_files，再决定 paper_language / report_generation_errors / report_session_result 的归位或删除方式。

## 2026-04-12 publish 第五批根级镜像删除

已完成：

- publish 顶层 report_output_files 已移除。
- report_output_files 的标准读取位统一收敛到 artifacts；不再保留根级字段，也不再作为 publish.results 的标准字段。
- phase_result 兼容归一化仍会把旧 payload 的 report_output_files 推导进 artifacts，但不会再把它保留在根级或 results.report_output_files。

回归验证：

- tests/test_citation_manager.py
- tests/test_phase_result_contract.py

当前 publish 根级剩余字段进一步收敛为：paper_language、report_session_result、report_generation_errors、analysis_results、research_artifact。

下一步可处理 paper_language、report_generation_errors、report_session_result，其中 analysis_results、research_artifact 继续保留为 publish 对外 DTO。

## 2026-04-12 publish 第六批根级镜像删除

已完成：

- publish 顶层 paper_language 已移除。
- paper_language 未迁入 metadata；由于仓内无消费者，直接删除更干净。
- phase_result 兼容归一化已补充 removed-field 过滤，旧 payload 中只有 paper_language 这类已删除兼容字段时，不会再把它们错误回填进 normalized.results。

回归验证：

- tests/unit/test_publish_phase.py
- tests/test_citation_manager.py
- tests/test_phase_result_contract.py

当前 publish 根级剩余字段进一步收敛为：report_session_result、report_generation_errors、analysis_results、research_artifact。

下一步可继续删除 report_generation_errors 与 report_session_result；analysis_results、research_artifact 继续保留为 publish 对外 DTO。

## 2026-04-12 publish 第七批根级镜像删除

已完成：

- publish 顶层 report_generation_errors 已移除。
- 失败态表达继续依赖标准契约：status=degraded，metadata.report_error_count 记录错误数量。
- phase_result 兼容归一化已将 report_generation_errors 纳入 removed-field 过滤，legacy payload 不会再把它保留在根级或 results。

回归验证：

- tests/unit/test_publish_phase.py
- tests/test_citation_manager.py
- tests/test_phase_result_contract.py

当前 publish 根级剩余字段进一步收敛为：report_session_result、analysis_results、research_artifact。

下一步可处理 report_session_result；analysis_results、research_artifact 继续保留为 publish 对外 DTO。

## 2026-04-12 publish 第八批根级镜像删除

已完成：

- publish 顶层 report_session_result 已移除。
- report_session_result 继续仅作为 publish 内部 report generator 输入快照存在，不再暴露为 publish 对外根级字段。
- phase_result 兼容归一化已将 report_session_result 纳入 removed-field 过滤，legacy payload 不会再把它保留在根级或 normalized.results。

回归验证：

- tests/unit/test_publish_phase.py
- tests/test_citation_manager.py
- tests/test_phase_result_contract.py

当前 publish 根级剩余字段进一步收敛为：analysis_results、research_artifact。

当前阶段可视为 publish 旧根级兼容镜像删除序列完成；analysis_results、research_artifact 继续保留为 publish 对外 DTO。

补充决策（2026-04-12）：

- analysis_results、research_artifact 不再纳入 publish 根级兼容字段删除线。
- publish_phase 内部仍保留一份仅供 ReportGenerator 消费的 report_session_payload，但它只是内部生成输入，不是对外 DTO，也不会再以 report_session_result 名义暴露。
- 后续如调整 publish 输出，应将它们视为稳定对外 DTO，而不是待删除的旧镜像字段。

## 2026-04-12 publish 第九批根级兼容字段删除

已完成：

- publish 顶层 analysis_results 已移除，标准读取位收敛为 results.analysis_results。
- publish 顶层 research_artifact 已移除，标准读取位收敛为 results.research_artifact。
- phase_result 兼容归一化会把 legacy payload 中的 analysis_results / research_artifact 合并进 normalized.results，同时过滤根级残留字段。
- orchestrator 的 publish 高亮提取已改为通过标准路径读取，因此最终 REST/Web 的 ResearchResult DTO 仍可继续在总结果根级暴露 analysis_results / research_artifact，而不再依赖 publish 根级镜像。

真实运行验证：

- output/research_session_1775971820.json 中，根 phase_results 六阶段的 metadata.deprecated_field_fallbacks 全部为空。
- 同一文件里，publish 根结果的剩余额外顶层字段只剩 analysis_results、research_artifact；本批删除后，publish 根级额外字段应归零。

回归验证：

- tests/unit/test_publish_phase.py
- tests/test_citation_manager.py
- tests/test_phase_result_contract.py
- tests/test_research_pipeline_quality.py
- tests/test_research_orchestrator.py

## 2026-04-12 publish 第十批大对象结果收敛

本批不是继续删除 publish 根级字段，而是收敛 publish.results 中的两块大对象：paper_draft、imrd_reports。

问题：

- 这两个字段虽然已经不在 publish 根级，但仍然作为 publish.results 的标准字段进入 session JSON。
- 在真实运行输出中，它们会随着 cycle_snapshot.phase_executions / outcomes / phase_history 被重复持久化，形成多份冗余拷贝。
- 真实样本 output/research_session_1775972206.json 中，这两类字段合计出现 8 次，主要来自 publish.results 及其快照镜像。

已完成：

- publish.results.paper_draft 已移除。
- publish.results.imrd_reports 已移除。
- 论文正文与 IMRD 报告的标准承载位统一收敛到 artifacts：
  - markdown / docx
  - imrd_markdown / imrd_docx
- 论文级轻量摘要继续保留在 results.publications 与 metadata.paper_review_summary，避免为了取 review_summary 等少量信息而继续持久化整份草稿对象。
- phase_result 兼容归一化已补充结果字段过滤：legacy payload 即使在 results 内仍带 paper_draft / imrd_reports，normalize 后也不会继续保留。
- 唯一非测试消费者 tools/diagnostics/compare_real_cycle_lexicon_modes.py 已改为从 markdown artifact 提取摘要与结果段，而不是依赖 publish.results.paper_draft。

回归验证：

- tests/unit/test_publish_phase.py
- tests/test_citation_manager.py
- tests/test_phase_result_contract.py
- tests/test_research_pipeline_quality.py

真实运行验证目标：

- 六阶段真实运行保持 completed。
- 根 phase_results 六阶段的 metadata.deprecated_field_fallbacks 继续为空。
- publish.results 中不再出现 paper_draft / imrd_reports。
- 新 session JSON 中这两个字段不再随着 cycle_snapshot 重复展开。