# 中医文献研究法视角的软件架构再审计与下一阶段设计

日期：2026-04-20

范围：本地部署的 Qwen1.5-7B-Chat Q8_0 GGUF、ResearchRuntimeService 七阶段科研主链、PostgreSQL / Neo4j 结构化持久化、文献学工作台、自学习闭环、小模型成本优化基础设施、Web / CLI 运行入口。

说明：桌面原始资料《中医文献研究法》未直接纳入当前工作区，本次评估沿用既有审计文档中已经提炼出的研究方法框架，并对当前仓库实现重新核对。本文是对 [ARCHITECTURE_TCM_RESEARCH_METHOD_AUDIT_2026_04_12.md](ARCHITECTURE_TCM_RESEARCH_METHOD_AUDIT_2026_04_12.md) 的更新版，不覆盖旧文档。

方法：静态代码审计、阶段主链重建、既有审计结论复核、阶段推进摘要复核、当前测试基线复核。

测试基线（2026-04-21 更新）：全量套件基线 3046+ passed / 0 failed / 4 xfailed / 2 skipped；G-3/G-4/H-1/H-2 推进后核心子集（tests/unit + test_research_session_repo + test_research_utils + test_web_console_api）**1385 passed / 0 failed**（H-2 阶段新增 31 个用例）。

---

## 1. 执行摘要

当前系统已经不应再被描述为“仅能跑演示的中医研究助手”。截至 2026-04-20，它已经具备以下平台化特征：

- 主入口已收口到 ResearchRuntimeService，CLI / Web / demo research 共用七阶段 runtime contract。
- PostgreSQL / Neo4j 已不仅是附属组件，而是主科研链的结构化资产沉淀底座，并加入了降级治理、回填账本和存储观测。
- 文献学主线已经完成目录学、训诂、辑佚、考据、工作台化五块首轮落地，并完成一轮精化。
- Reflect 已从“总结阶段”进入“学习阶段”，能把反馈沉淀为可查询、可回放的学习资产，并对下一轮策略产生真实影响。
- 面向本地小模型的成本控制基础设施已经补齐，Qwen1.5-7B-Chat Q8_0 的使用方式开始从“直接调用模型”转向“推理模板选择 + 动态调用策略 + 分层 dossier 压缩”。

如果目标是“单机、本地、可追溯的中医文献科研平台”，当前架构已经成立。如果目标是“多研究者协作、强运维、强评测、强知识图谱治理的平台”，当前还缺三段最后一公里：

1. 跨阶段协议的最终统一，尤其是把阶段产物进一步收口为更稳定的共享 envelope。
2. 可观测与运维导出的最后收口，尤其是把内部治理状态变成可直接消费的外部指标与告警面。
3. 图谱资产与人工复核闭环的二期深化，尤其是把假说、证据和文献学校核结果做成更稳定的可比资产。

我的判断是：该系统已从“半自动科研助手”跨入“本地平台雏形”，架构方向正确，最难的第一轮边界工程已经完成，后续主要是治理深化，而不是推倒重来。

---

## 2. 以《中医文献研究法》衡量当前实现度

既有审计把《中医文献研究法》提炼为三层：文献学研究、类编研究、学术研究。按当前代码现状重新估算如下。

| 方法论层级 | 当前实现度 | 当前判断 | 主要依据 |
| --- | ---: | --- | --- |
| 文献学研究 | 92% | 已从“文本预处理附属能力”升级为独立主线 | catalog_contract、exegesis_contract、fragment_contract、textual_evidence_chain、review workbench、catalog summary、version lineage / witness 结构化沉淀 |
| 类编研究 | 84% | 仍是成熟层，但下一步重点从“能抽取”转向“能治理” | 实体抽取、语义图谱、统计分析、evidence contract、Neo4j 投影、结构化 snapshot、dashboard 查询面 |
| 学术研究 | 88% | 七阶段链条已经成立，真实边界比旧版更清晰 | hypothesis engine、experiment / experiment_execution 拆分、analyze 证据协议、publish 交付链、reflect 学习反馈库、policy adjuster |

### 2.1 文献学研究

当前系统在文献学上已经不只是做术语标准化，而是具备以下五块稳定能力：

- 目录学：作品、片段、版本谱系、见证本键空间已成型。
- 训诂：支持术语释义、义项判别、时代语义与来源强弱分层。
- 辑佚：可生成 fragment candidates、lost text candidates、citation source candidates。
- 考据：支持作者归属、版本先后、引文来源三类 claim 与证据链。
- 工作台化：review status、筛选、回写、audit trail 已形成最小闭环。

不足不再是“有没有这些模块”，而是：

- 义项与考据精度仍偏规则驱动，缺少更强权威源和批量校核策略。
- 工作台已能用，但还不具备大规模人工复核的批处理效率。
- 文献学资产已能沉淀，尚未完全变成跨会话、可比较、可统计的研究底座。

### 2.2 类编研究

这一层仍然是当前系统最稳定的一层，因为它已经把文本、实体、关系、统计、图谱、artifact 和 snapshot 连成了可运行链路。其优势在于：

- Observe -> Analyze -> Publish 的结构化结果已经可以被下游复用。
- Neo4j 与 PostgreSQL 已分别承担图投影与事务事实存储。
- Evidence protocol、dashboard payload、repository snapshot 之间的共享 contract 已明显优于早期状态。

当前真正缺的不是再加一个 extractor，而是：

- 图谱 schema 版本化与变更治理。
- 假说子图、证据子图、文献学子图之间的显式映射。
- 面向回归和评测的稳定 benchmark 资产。

### 2.3 学术研究

七阶段已经从概念链变成真实执行链：

- Observe：采集、清洗、NER、语义图谱、文献学聚合。
- Hypothesis：KG-enhanced、LLM、rules 三路径回退。
- Experiment：收口为 protocol design。
- ExperimentExecution：承接外部实验执行结果导入与质量校验。
- Analyze：统计、推理框架、证据分级、evidence protocol。
- Publish：论文草稿、IMRD、引用与结构化交付。
- Reflect：质量评估、学习反馈、策略调整与下一轮参数输入。

学术层的剩余短板也已经变化：

- 最大短板不是“没有反思”或“没有写作”，而是“跨阶段共享协议与评测面仍未完全统一”。
- 最大边界不是“不会做实验”，而是“系统明确不在内部自动执行真实实验”。
- 最大优化空间不是“换更大模型”，而是“把小模型优化基础设施真正用成默认执行策略”。

---

## 3. 核心模块与当前状态

| 模块 | 关键文件 | 状态 | 实现度 | 评语 |
| --- | --- | --- | ---: | --- |
| 统一运行入口 | src/orchestration/research_runtime_service.py | active | 91% | 已成为主科研链事实入口，兼容壳问题已基本治理完毕 |
| 运行配置装配 | src/infrastructure/runtime_config_assembler.py | active | 89% | 运行 profile 统一效果明显，残余重点是防止新的旁路回流 |
| 科研内核 | src/research/research_pipeline.py | active | 88% | 七阶段与持久化主链已稳定，但仍是重量级中枢 |
| 阶段编排 | src/research/phase_orchestrator.py | active | 87% | 阶段执行、structured persist、metadata 汇总已接入主链 |
| 文献学主线 | src/analysis/philology_service.py 等 | active | 90% | 已形成独立研究资产链，不再只是 observe 附属能力 |
| 证据协议 | src/research/evidence_contract.py | active | 83% | Analyze / Publish / 输出层已显著收口，但尚未完全成为所有 phase 的统一 envelope |
| 学习闭环 | src/research/learning_loop_orchestrator.py、src/learning/policy_adjuster.py | active | 86% | 已从 reflect 摘要升级为下一轮策略输入 |
| 存储治理 | src/storage/backend_factory.py、degradation_governor.py、backfill_ledger.py、storage_observability.py | active | 88% | 治理基础设施已补齐，下一步是导出与运维面 |
| 小模型优化 | src/infra/reasoning_template_selector.py 等 | active | 84% | 基础设施到位，仍需扩大默认消费面与评测面 |
| Web / Dashboard | src/web、src/api | active | 80% | 已接入研究资产与 review 面，但仍偏单机工作台而非协作平台 |
| 运维 / CI / 评测 | docs、tools、tests | partial | 68% | 测试强，导出与门禁仍偏工程内视角 |

这张表的核心结论是：现在最弱的层不是研究链，也不是文献学层，而是“平台外壳”层，也就是运维导出、评测基线、批量人工复核效率与图谱治理。

---

## 4. 真实科研工作流是否已经成立

答案是：已经成立，但边界必须说准。

### 4.1 当前真实可执行链

```mermaid
flowchart TD
    ENTRY[CLI / Web / Demo] --> RUNTIME[ResearchRuntimeService]
    RUNTIME --> PIPELINE[ResearchPipeline]
    PIPELINE --> OBSERVE[Observe]
    OBSERVE --> HYPOTHESIS[Hypothesis]
    HYPOTHESIS --> EXPERIMENT[Experiment: Protocol Design]
    EXPERIMENT --> EXECUTION[ExperimentExecution: External Result Import]
    EXECUTION --> ANALYZE[Analyze]
    ANALYZE --> PUBLISH[Publish]
    PUBLISH --> REFLECT[Reflect]
    REFLECT --> LEARN[LearningLoopOrchestrator / PolicyAdjuster]
    LEARN --> NEXT[Next Cycle Strategy]
    OBSERVE --> PG[(PostgreSQL)]
    ANALYZE --> PG
    PUBLISH --> PG
    REFLECT --> PG
    OBSERVE --> NEO[(Neo4j)]
    ANALYZE --> NEO
    PUBLISH --> FS[Artifacts / Reports]
```

### 4.2 它今天能做什么

- 能把一个研究问题推进成七阶段的结构化研究会话。
- 能在 observe 阶段完成采集、预处理、实体抽取、语义建模与文献学资产化。
- 能在 hypothesis 阶段依据知识图谱、规则和 LLM 生成候选假说。
- 能在 experiment 阶段形成结构化 protocol，而不是模糊地把实验与分析混在一起。
- 能在 experiment_execution 阶段承接外部执行结果导入，并进行质量校验。
- 能在 analyze / publish / reflect 阶段形成证据、写作与学习资产。
- 能把关键资产沉淀到 PostgreSQL / Neo4j / artifacts，而不是只吐出一个最终 markdown。

### 4.3 它今天不能被误描述为什么

- 不是系统内自动完成真实实验的平台。
- 不是已经完成知识图谱版本治理和研究 benchmark 的成熟中台。
- 不是多人协作的文献学审核生产系统。

### 4.4 真实边界的正确说法

更准确的描述应该是：

“这是一个本地部署的中医文献研究平台雏形，已经能完成研究设计、外部实验结果导入、证据分析、学术输出和学习反馈，但真实实验执行、图谱治理和大规模人工复核仍在系统外或二期范围内。”

---

## 5. 针对本地 Qwen1.5-7B-Chat Q8_0 的专项评估

本地模型部分的架构结论与 2026-04-12 已经不同。之前主要问题是“多处直接调模型，缺少统一策略”；现在已经进入“基础设施到位，等待默认消费面扩张”的阶段。

### 5.1 已经完成的关键建设

- ReasoningTemplateSelector：为不同 phase 和问题复杂度选择更合适的推理框架。
- DynamicInvocationStrategy：把调用策略从“总是调用”变成“继续、拆分、跳过、简化重试”的动态决策。
- DossierLayerCompressor：为 7B 小模型做三层上下文压缩。
- SmallModelOptimizer：把模板选择、调用策略、上下文压缩聚合为 prepare_call() 级别的统一规划器。
- PolicyAdjuster 桥接：下一轮策略可直接影响 template preference 与 budget 决策。

### 5.2 这意味着什么

它意味着当前系统已经不再把本地 Qwen 当成“裸模型”，而是开始把它当成“受控推理资源”。这一步在本地科研平台里非常关键，因为问题从来不是模型能否回答，而是：

- 它在预算内是否稳定。
- 它对不同阶段是否用不同思维模板。
- 它是否优先消费结构化 dossier，而不是直接读一大堆原文。

### 5.3 仍然不足的地方

- 小模型优化基础设施并未完全成为所有 LLM 调用的唯一执行面。
- 缺少稳定的 phase-level 评测集来验证模板选择和 budget policy 是否真的提升质量。
- 目前更像“已具备优秀执行策略内核”，还不是“全链默认启用的小模型治理系统”。

---

## 6. 当前架构的主要优点与主要约束

### 6.1 主要优点

- 阶段边界已经成熟，尤其是 experiment 与 experiment_execution 的语义边界已经统一。
- 文献学能力已经进入主链，不再是零散 artifact。
- 存储主链已经从“写文件”升级为“结构化研究资产沉淀”。
- Reflect 已具备真实反馈价值，而不是仅生成总结文本。
- 小模型优化思路正确，且已经有具体工程载体，不是停留在 PPT。

### 6.2 主要约束

- 共享协议仍有最后一公里，部分 phase 的产物仍保留各自历史形状。
- 存储治理更多体现在内部 contract 和测试，外部运维导出面还不够强。
- 图谱已能写入，但假说、证据、文献学资产之间的显式图模型还不够稳定。
- 工作台已能审核，但还不够适合大规模批量复核。
- 测试数量很多，但平台级 benchmark、coverage gate、nightly smoke 仍未完全制度化。

---

## 7. 建议的目标架构

### 7.1 边界上下文

建议把当前平台长期固定为八个上下文：

1. Runtime Orchestration：统一 CLI / Web / Batch 入口。
2. Literature Philology：目录学、训诂、辑佚、考据、review workbench。
3. Corpus Structuring：清洗、分段、实体、关系、索引。
4. Research Design：观察、假说、实验协议设计。
5. Research Analysis：统计、证据、推理、图谱分析。
6. Publication Delivery：论文、IMRD、引用、artifact 输出。
7. Learning Governance：质量评估、反思、策略调整、成本治理。
8. Research Asset Storage：PostgreSQL、Neo4j、artifact repository、snapshot / backfill / observability。

### 7.2 建议的能力拓扑

```mermaid
flowchart LR
    CLI[CLI] --> RT[Runtime Orchestration]
    WEB[Web / Dashboard] --> RT
    BATCH[Batch / Scheduler] --> RT

    RT --> PHILO[Literature Philology]
    RT --> STRUCT[Corpus Structuring]
    RT --> DESIGN[Research Design]
    RT --> ANALYSIS[Research Analysis]
    RT --> PUB[Publication Delivery]
    RT --> GOV[Learning Governance]

    PHILO --> STORE[(PostgreSQL)]
    STRUCT --> STORE
    DESIGN --> STORE
    ANALYSIS --> STORE
    ANALYSIS --> GRAPH[(Neo4j)]
    PUB --> ARTIFACT[Artifact Repository]
    GOV --> STORE
    GOV --> METRIC[Metrics / Audit / Alerts]
    GRAPH --> GOV
```

### 7.3 建议的核心契约

```mermaid
classDiagram
    class ResearchSessionRequest {
      +question
      +phase_list
      +runtime_profile
      +storage_profile
      +learning_strategy
    }

    class PhaseResult {
      +phase
      +status
      +results
      +artifacts
      +metadata
      +error
    }

    class EvidenceEnvelope {
      +protocol_version
      +evidence_records
      +claims
      +citation_records
      +grade_summary
    }

    class LearningFeedbackLibrary {
      +cycle_summary
      +phase_assessment
      +replay_feedback
      +tuned_parameters
    }

    class StorageConsistencyState {
      +mode
      +pg_status
      +neo4j_status
      +summary
      +schema_drift_detected
    }

    ResearchSessionRequest --> PhaseResult
    PhaseResult --> EvidenceEnvelope
    PhaseResult --> LearningFeedbackLibrary
    PhaseResult --> StorageConsistencyState
```

### 7.4 本地部署目标形态

```mermaid
flowchart TD
    USER[Researcher] --> APP[TCM Research App]
    APP --> MODEL[Qwen1.5-7B-Chat Q8_0\nllama-cpp-python]
    APP --> PG[(PostgreSQL)]
    APP --> NEO[(Neo4j Community 5.26.x)]
    APP --> FILES[Artifacts / Reports / Cache]
    APP --> OPS[Observability / Backfill / Health Check]
    PG --> OPS
    NEO --> OPS
```

---

## 8. 具体优化建议

下面只列真正值得进入下一阶段 backlog 的建议，每条都给出明确的理由和代价。

| 优先级 | 建议 | 理由 | 代价 |
| --- | --- | --- | --- |
| P0 | 把 EvidenceEnvelope 扩展为更完整的跨阶段共享协议 | 当前 Analyze / Publish 已显著收口，但 Observe、Hypothesis、ExperimentExecution 仍存在历史产物形状；这会增加 API、snapshot、report 和 replay 的认知成本 | 中，3-5 人日 |
| P0 | 为 StorageObservability / DegradationGovernor 增加 Prometheus 或等价导出面 | 当前治理能力已经在代码内存在，但外部运维还难以直接消费；没有导出面，就难把“已治理”变成“可值守” | 中，2-4 人日 |
| P0 | 为 Neo4j 建立 schema versioning 与 hypothesis / evidence 子图模型 | 现在图谱可用，但研究资产在图层仍偏投影式，不够稳定；没有 schema versioning，后续图演进会越来越难 | 中高，4-6 人日 |
| P1 | 把 philology review workbench 升级为批量复核工作流 | 目前 review 已能写回，但更像单条审核；如果要支撑真实研究积累，需要批量筛选、批量决策、批量审计与 reviewer 负载视图 | 中高，4-6 人日 |
| P1 | 让 SmallModelOptimizer 成为默认 LLM 规划层，并补 phase-level 评测集 | 现在基础设施正确，但还没有完全变成默认执行路径；没有评测集，就难证明策略优于简单 prompt 调用 | 中，3-5 人日 |
| P1 | 建立 nightly smoke + coverage gate + known-failure 白名单机制 | 当前回归基线强，但制度化不足；把 2893 pass / 4 known failures 固化到 CI，才能真正防止平台回退 | 中，2-4 人日 |
| P2 | 建立跨 cycle 的研究资产对比视图 | 文献学、证据、学习反馈都已经能沉淀，但目前更偏单 cycle 查询；如果要做研究积累，需要把“会话”升级为“可比较资产集” | 中，3-5 人日 |
| P2 | 为本地 Qwen 增加任务分层 benchmark | 现在知道模型适合什么，不代表能持续证明；benchmark 能让模板选择、budget policy、fallback 策略从经验走向证据 | 中，2-3 人日 |

### 8.1 优先级解释

P0 的共同特点是：不做会直接影响平台可持续性。P1 的共同特点是：不做平台仍能跑，但效率和稳定性会逐渐成为瓶颈。P2 的共同特点是：它们会明显提升“研究平台感”，但不是当前主链成立的阻塞项。

---

## 9. 分阶段实施计划

### 9.1 已完成阶段

| 阶段 | 状态 | 结果 |
| --- | --- | --- |
| Phase A | 已完成 | 入口收口，ResearchRuntimeService 成为主运行入口 |
| Phase B | 已完成 | 存储治理补齐 DegradationGovernor / BackfillLedger / StorageObservability |
| Phase C | 已基本完成首轮 | 文献学五块主线已落地并完成一轮深化 |
| Phase D | 已完成 | 学习闭环、导入质量校验与下一轮策略接线完成 |
| Phase E | 已完成 | 小模型成本优化四件套与单例入口补齐 |
| Phase F-4 | 已完成 | Known-failure 白名单机制、conftest.py --strict-known-failures |
| Phase G-1 | 已完成 | Neo4j schema versioning、标签注册表、KG stats schema/drift 输出、实体 type -> label 映射统一完成 |
| Phase G-2 | 已完成首轮 | hypothesis / evidence graph assets 已接入 phase result、统一事务投影、统计输出与回归守卫 |
| Phase G-3 | 已完成 | 文献学子图治理：Catalog / ExegesisTerm / FragmentCandidate / TextualEvidenceChain 节点注册、philology graph assets 输出、review 复核元数据同步图属性、查询模板 |
| Phase G-4 | 已完成 | 图回归检查与历史资产 backfill：schema v2 backfill、production-local preflight dry-run（703 nodes / 1393 edges）、Guard #37 |
| Phase H-1 | 已完成 | Review queue 与批量复核工作台：queue/summary/filter contract、多选批量写回、batch audit fields，新增 18 个测试，单元套件 1234 passed |
| Phase H-2 | 已完成 | Reviewer 分配与负载视图：ReviewAssignment ORM + alembic `b5d8a91e3c47`、claim/release/reassign/complete/list/aggregate API、三视图看板（我负责 / 无人认领 / 超期项），新增 31 个测试，核心子集 1385 passed |
| Phase I-1 | 已基本完成 | SmallModelOptimizer planner 接线 hypothesis / reflect / quality / experiment / publish |
| 代码质量治理 | 已完成 | Cypher injection / Neo4j 资源泄漏 / 配置重复键 / filterwarnings / 测试 tearDown (04-21) |

### 9.2 下一阶段建议

#### Phase F：协议与可观测收口

- 目标：把共享 contract 和外部运维面同时做扎实。
- 动作：扩展 EvidenceEnvelope、收口 phase output 形状、增加 metrics export、固化 known-failure 白名单。
- 理由：这是从“工程内可维护”变成“平台级可维护”的关键一段。
- 代价：中，约 1 周。

##### Phase F 可执行任务清单

> 下面四条子线无硬依赖，可并行推进。F-1 影响面最广，建议先落地。

---

###### F-1 EvidenceEnvelope 跨阶段协议统一

当前只有 analyze_phase 调用 `build_evidence_protocol()` 产出 canonical `evidence-claim-v2`。observe / hypothesis / experiment / experiment_execution / reflect 仍使用各自 ad-hoc dict。目标是让所有 phase 的产出都能被统一 envelope 消费。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| F-1-1 | 为 EvidenceEnvelope 补充 `phase_origin` 字段，标记证据来源阶段 | `src/research/evidence_contract.py` | 新增字段 + `to_dict()` / `from_dict()` 往返一致 |
| F-1-2 | observe_phase 产出的 findings/observations 按 EvidenceEnvelope 归并，以 `evidence_grade = "preliminary"` 标注 | `src/research/phases/observe_phase.py`、`src/research/evidence_contract.py` | observe 的 `results["evidence_protocol"]` 存在且 `contract_version == "evidence-claim-v2"` |
| F-1-3 | hypothesis_phase 产出的 hypotheses 按 EvidenceEnvelope 归并为 claim 层 | `src/research/phases/hypothesis_phase.py`、`src/research/evidence_contract.py` | hypothesis 的 `results["evidence_protocol"]` 存在，每个 hypothesis 映射为 1 条 claim |
| F-1-4 | experiment_execution_phase 产出的 execution_records / analysis_records 按 EvidenceEnvelope 归并为 record 层 | `src/research/phases/experiment_execution_phase.py`、`src/research/evidence_contract.py` | execution 的 `results["evidence_protocol"]` 存在且 record_count > 0 |
| F-1-5 | reflect_phase 产出的 quality_assessment 按 EvidenceEnvelope 归并为 grade_summary 补充 | `src/research/phases/reflect_phase.py`、`src/research/evidence_contract.py` | reflect 的 `metadata["evidence_protocol_contributed"]` = true |
| F-1-6 | PhaseResult 通用层新增 `get_evidence_protocol()` helper | `src/research/phase_result.py` | 对所有已迁移 phase 的 PhaseResult 调用 `.get_evidence_protocol()` 返回非 None |
| F-1-7 | 架构回归守卫：所有 phase 的 results 必须含 `evidence_protocol` 键 | `tests/unit/test_architecture_regression_guard.py` (新 Guard #34) | Guard #34 AST 检查每个 phase mixin 的 `_build_phase_result` 调用路径包含 evidence_protocol |

测试文件：

- `tests/unit/test_evidence_contract_v2.py`（新建，≥ 20 tests）
- `tests/unit/test_phase_evidence_envelope.py`（新建，覆盖 7 phase × envelope 一致性）

---

###### F-2 StorageObservability / DegradationGovernor Prometheus 导出

当前 `MonitoringService`（src/infrastructure/monitoring.py）已有 prometheus_client registry 和 `/metrics/prometheus` 端点，但完全不消费 `StorageObservability.get_health_report()` 和 `DegradationGovernor.to_governance_report()`。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| F-2-1 | MonitoringService 接入 StorageObservability：新增 Gauge `tcm_storage_health_score`、`tcm_storage_success_rate`、`tcm_storage_latency_p95_ms`、`tcm_storage_backfill_pending` | `src/infrastructure/monitoring.py`、`src/storage/storage_observability.py` | `/metrics/prometheus` 输出包含以上 4 个 gauge |
| F-2-2 | MonitoringService 接入 DegradationGovernor：新增 Gauge `tcm_storage_mode` (枚举 label)、`tcm_storage_is_degraded`、`tcm_storage_failure_rate`、`tcm_storage_compensations_total` | `src/infrastructure/monitoring.py`、`src/storage/degradation_governor.py` | `/metrics/prometheus` 输出包含以上 4 个 gauge |
| F-2-3 | config.yml 新增 `monitoring.storage_governance: true` 开关 | `config.yml`、`config/production.yml`、`src/infrastructure/monitoring.py` | 配置关闭时上述 gauge 不注册 |
| F-2-4 | Web API 补充 `/api/storage/health` JSON 端点，直接返回 `get_health_report()` + `to_governance_report()` 合并结果 | `src/api/routes/system.py` | HTTP GET 返回合并 JSON；无 factory 时返回 503 |

测试文件：

- `tests/unit/test_storage_metrics_export.py`（新建，≥ 12 tests，mock factory）
- `tests/test_web_console_api.py`（追加 storage health 端点测试）

---

###### F-3 Phase output 形状收口

当前 7 个 phase 的 `results` / `metadata` 键名差异大（experiment 有 20+ 键，observe 有 5 键）。目标不是强制统一字段，而是建立最小公约契约。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| F-3-1 | 定义 `PHASE_RESULT_COMMON_KEYS`：results 至少包含 `evidence_protocol`、`summary`；metadata 至少包含 `learning`、`learning_strategy_applied`、`contract_version` | `src/research/phase_result.py` | 常量可导入，`build_phase_result()` 自动注入缺失的 common keys 为 None |
| F-3-2 | observe_phase 补 `metadata.learning` + `metadata.learning_strategy_applied` | `src/research/phases/observe_phase.py` | observe PhaseResult metadata 含以上两个键 |
| F-3-3 | reflect_phase 清理 `extra_fields` 冗余：去掉与 results 完全重复的顶层键 | `src/research/phases/reflect_phase.py` | reflect PhaseResult 的顶层 dict 不再包含 results 内已存在的键 |
| F-3-4 | experiment_phase 对 results 做分层：把 20+ 平铺键收敛到 `protocol_design` 子对象 + `execution_boundary` 子对象 | `src/research/phases/experiment_phase.py` | results 顶层键 ≤ 8 个，旧键以兼容 alias 保留 |
| F-3-5 | 架构回归守卫：所有 phase 的 metadata 必须含 `learning` 和 `contract_version` | `tests/unit/test_architecture_regression_guard.py` (新 Guard #35) | Guard #35 对 7 个 phase mixin 断言 metadata 公约 |

测试文件：

- `tests/unit/test_phase_output_shape.py`（新建，≥ 14 tests，覆盖 7 phase × common-key 一致性）
- 旧消费方回归：`tests/test_research_utils.py`、`tests/test_web_console_api.py`、`tests/unit/test_dashboard_copy.py`

---

###### F-4 Known-failure 白名单机制 ✅ 已完成

当前 4 个已知失败只在 STAGE_PROGRESS 文档里以文字记录，没有任何代码层面的管理。目标是把它们固化到 pytest 配置里，让 CI 能明确区分"预期失败"和"意外回归"。**（2026-04-21 已全部落地）**

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| F-4-1 | pyproject.toml 注册 `known_failure` 自定义 marker | `pyproject.toml` | `[tool.pytest.ini_options] markers = ["known_failure: ..."]` |
| F-4-2 | 为 4 个已知失败添加 `@pytest.mark.xfail(reason=..., strict=False)` | `tests/test_gap_analyzer.py`（2 处）、`tests/test_hypothesis_engine.py`（1 处）、`tests/test_web_console_browser_e2e.py`（1 处） | 标记后全量回归：xfail 4 + pass ≥ 2893 + skip 2 |
| F-4-3 | 新增 `tests/conftest.py`，添加 `--strict-known-failures` 自定义选项：开启后 xfail 变 strict，在预期失败修复后自动从白名单移除 | `tests/conftest.py`（新建） | `pytest --strict-known-failures` 运行时 4 个 xfail 标记会 strict 执行 |
| F-4-4 | 回归基线文档化：在 pyproject.toml 补充 `[tool.pytest.ini_options] minversion` 和回归计数注释 | `pyproject.toml` | 注释明确 `# baseline: 2893 pass / 4 xfail / 2 skip` |

测试文件：

- 无需新建测试文件，修改现有 4 个测试文件 + 新建 `tests/conftest.py`
- 验收命令：`venv310\Scripts\python.exe -m pytest tests/ -q --tb=line`，确认 xfail=4 + pass ≥ 2893

#### Phase G：图谱资产治理

- 目标：把图谱从“研究投影”升级为“研究资产模型”。
- 动作：建立 schema versioning、假说子图、证据子图、文献学子图，以及图回归检查。
- 理由：当前 PG 已经很强，图谱要真正发挥作用，必须从可写入变成可治理。
- 代价：中高，约 1-2 周。

##### Phase G 可执行任务清单

> 建议按 G-1 -> G-2 -> G-3 -> G-4 顺序推进。G-1 提供 schema 基线，G-2 / G-3 复用同一标签注册表，G-4 把图治理要求固化到 backfill 与回归检查。

---

###### G-1 Neo4j schema versioning 与标签注册表

当前 `_project_cycle_to_neo4j()` 只把 session / phase / artifact / observe 实体投影到图里，标签与关系类型散落在 `phase_orchestrator.py`、`research_session_graph_backfill.py`、`neo4j_driver.py` 中，没有统一 schema registry，也没有版本漂移可见性。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| G-1-1 | 新增图谱 schema 注册表，集中定义 `GRAPH_SCHEMA_VERSION`、资产节点标签、关系类型、允许属性白名单 | `src/storage/graph_schema.py`（新建）、`src/storage/graph_interface.py` | 可导入 registry，至少覆盖 `ResearchSession`、`ResearchPhaseExecution`、`ResearchArtifact`、`Hypothesis`、`Evidence`、`EvidenceClaim`、`Catalog`、`VersionLineage`、`VersionWitness` |
| G-1-2 | `Neo4jDriver.connect()` 增加 schema bootstrap：写入 `GraphSchemaMeta`（或等价 metadata 节点），并提供 `get_schema_version()` / `ensure_schema_version()` | `src/storage/neo4j_driver.py`、`src/storage/backend_factory.py` | 启用 Neo4j 后可读取当前 schema version；version mismatch 时返回 drift 报告 |
| G-1-3 | `phase_orchestrator` 与 `research_session_graph_backfill` 改为通过 schema registry 取 label / relationship_type，不再在多处散落硬编码字符串 | `src/research/phase_orchestrator.py`、`src/research/research_session_graph_backfill.py`、`src/storage/graph_schema.py` | 现有 session / phase / artifact / observe 图投影全部经 registry helper 生成 |
| G-1-4 | KG 统计接口补充 `schema_version`、`schema_drift_detected`、`graph_projection_scope` 输出 | `src/api/routes/analysis.py`、`src/storage/backend_factory.py`、`src/storage/neo4j_driver.py` | `GET /api/analysis/kg/stats` 返回 schema version 与 drift 状态 |

测试文件：

- `tests/unit/test_graph_schema_versioning.py`（新建，≥ 12 tests）
- `tests/unit/test_neo4j_driver.py`（追加 schema bootstrap / drift 检查）
- `test_kg_e2e.py`（追加 KG stats schema version 断言）

---

###### G-2 假说 / 证据子图资产化

当前 `hypothesis_phase` 只在内存里用 `create_knowledge_graph()` 构图；`evidence_contract` 已形成 canonical envelope，但 Analyze 的 claim / record 尚未映射成可治理的 Neo4j 研究资产。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| G-2-1 | 在 schema registry 中注册 `Hypothesis`、`Evidence`、`EvidenceClaim` 节点及 `HAS_HYPOTHESIS`、`EVIDENCE_FOR`、`SUPPORTED_BY`、`CONTRADICTS`、`DERIVED_FROM_PHASE` 等关系类型 | `src/storage/graph_schema.py`、`src/storage/graph_interface.py` | 新标签与关系类型均可通过 registry 校验 |
| G-2-2 | `hypothesis_phase` 新增 hypothesis subgraph payload builder，把候选假说、依赖实体、关系边输出为结构化 `graph_assets` | `src/research/phases/hypothesis_phase.py`、`src/research/phase_result.py` | hypothesis PhaseResult 含 `results["graph_assets"]["hypothesis_subgraph"]`，且 hypothesis_count > 0 时 node_count / edge_count > 0 |
| G-2-3 | `analyze_phase` 基于 `EvidenceEnvelope` 映射 evidence / claim 子图，并把 `textual_evidence_chain` 的 provenance 归到图边与节点属性 | `src/research/evidence_contract.py`、`src/research/phases/analyze_phase.py`、`src/analysis/textual_evidence_chain.py`、`src/research/research_session_graph_backfill.py` | 每条 claim 至少映射 1 个 `EvidenceClaim` 节点，`evidence_ids` 能回链到 `Evidence` 节点 |
| G-2-4 | 主持久化路径接管 hypothesis / evidence 子图投影，统一走 `factory.transaction()` / `TransactionCoordinator`，不回退到已弃用 `storage_driver.py` | `src/research/phase_orchestrator.py`、`src/storage/transaction.py`、`src/storage/backend_factory.py`、`src/storage/neo4j_driver.py` | 图写入失败时 PG 不提交；`graph_report` 新增 hypothesis / evidence node/edge 计数 |

测试文件：

- `tests/unit/test_graph_asset_subgraphs.py`（新建，≥ 16 tests）
- `tests/unit/test_architecture_regression_guard.py`（新 Guard #36，约束 hypothesis/analyze 必须产出 graph_assets）
- `test_kg_e2e.py`（追加 hypothesis / evidence 资产子图查询）

---

###### G-3 文献学子图治理

当前图里已有 `VersionLineage` / `VersionWitness` 投影基础，但 catalog / exegesis / fragment / textual evidence chain 仍主要停留在 PG / artifact / response payload，未形成稳定的文献学子图。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| G-3-1 | 在 schema registry 中注册 `Catalog`、`ExegesisTerm`、`FragmentCandidate`、`TextualEvidenceChain` 等节点，以及 `HAS_VERSION`、`ATTESTS_TO`、`INTERPRETS`、`RECONSTRUCTS`、`CITES_FRAGMENT` 等关系 | `src/storage/graph_schema.py`、`src/research/catalog_contract.py`、`src/research/exegesis_contract.py`、`src/research/fragment_contract.py` | 文献学三大合同字段能映射到图标签和关系类型 |
| G-3-2 | `observe_philology` / `philology_service` 输出标准化 philology graph assets，并与现有 `VersionLineage` / `VersionWitness` 节点打通 | `src/research/observe_philology.py`、`src/analysis/philology_service.py`、`src/analysis/textual_evidence_chain.py`、`src/research/research_session_graph_backfill.py` | observe 存在 philology summary 时，图中可查询到 catalog -> witness -> fragment / exegesis 链路 |
| G-3-3 | review workbench 的 `review_status`、`needs_manual_review`、`decision_basis` 等复核元数据同步进 philology 资产节点属性，支持后续 Phase H 批量治理 | `src/research/review_workbench.py`、`src/infrastructure/research_session_repo.py`、`src/research/research_session_graph_backfill.py` | 图节点属性中可直接筛选 accepted / rejected / needs_source / pending |
| G-3-4 | 为文献学子图补充标准查询模板，覆盖目录谱系、辑佚候选、争议证据链三类读取面 | `tools/neo4j_query_templates.py`、`src/api/routes/analysis.py` | 新模板全部通过 query governance 校验，且 `/api/analysis/kg/subgraph` 可新增 philology asset graph_type |

测试文件：

- `tests/unit/test_philology_graph_projection.py`（新建，≥ 14 tests）
- `tests/unit/test_neo4j_query_governance.py`（追加 philology 子图模板自校验）
- `tests/unit/test_textual_evidence_chain.py`、`tests/unit/test_catalog_contract.py`（追加 graph asset 映射断言）

---

###### G-4 图回归检查与历史资产 backfill

Phase G 如果只补模型、不补回归和回填，图谱会继续停留在“新数据可用、老数据漂移、查询面不稳定”的状态。需要把 schema versioning 和子图模型固化到可重复验证的 baseline。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| G-4-1 | 扩展 `research_session_graph_backfill`，为旧 cycle 生成 schema v2 的 hypothesis / evidence / philology graph assets | `src/research/research_session_graph_backfill.py`、`src/research/phase_orchestrator.py` | 对已有 session 执行 backfill 后，新增资产节点/边数量 > 0 且不破坏原有 session / observe 投影 |
| G-4-2 | 生产本地 backfill 脚本补充 graph schema version 参数与 dry-run 摘要，确保迁移前可预估 node/edge 变化 | `.vscode/production-local-backfill.ps1`、`tools/`（如需新增 graph backfill helper） | 预检输出包含 schema version、预计新增节点数、预计新增边数 |
| G-4-3 | 新增图回归守卫：校验 schema registry、核心标签计数、必备关系类型、KG stats schema version 输出 | `tests/unit/test_architecture_regression_guard.py`（新 Guard #37）、`tests/unit/test_graph_asset_regression.py`（新建） | 回归测试能在 schema 丢失、关系重命名、stats 漏字段时直接失败 |
| G-4-4 | 端到端回归扩展为资产级查询：验证 hypothesis / evidence / philology 三类 graph_type 与 stats 结果一致 | `test_kg_e2e.py`、`src/api/routes/analysis.py` | E2E 脚本能输出三类资产子图统计，且节点/边数与 `/api/analysis/kg/stats` 相互印证 |

测试文件：

- `tests/unit/test_graph_asset_regression.py`（新建，≥ 12 tests）
- `tests/unit/test_architecture_regression_guard.py`（新增 Guard #37）
- `test_kg_e2e.py`（追加资产级回归步骤）

#### Phase H：文献学人工复核二期

- 目标：把 philology review 从最小闭环升级为高效工作台。
- 动作：批量审核、review queue、reviewer 负载、争议归档、抽样质检。
- 理由：文献学层的瓶颈已经从算法缺位转向人工复核效率。
- 代价：中高，约 1-2 周。

##### Phase H 可执行任务清单

> 建议按 H-1 -> H-2 -> H-3 -> H-4 顺序推进。H-1 先把 queue / batch contract 做出来，H-2 补分配与负载，H-3 补争议闭环，H-4 再把抽样质检和质量面制度化。

---

###### H-1 Review queue 与批量复核工作台

当前 `review_workbench` 已有 section/card 结构、单条写回、批量写回 API，以及按作品 / 谱系 / 见证本 / review_status 的筛选；但 payload 仍以“卡片列表”视角为主，没有显式 `review_queue` 合同，`web_console/static/index.html` 虽已有 `submitBatchPhilologyReview()` helper，toolbar 仍只有筛选，没有真正的多选批处理工作流。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| H-1-1 | 为 dashboard payload 新增 `review_queue` / `queue_summary` / `queue_filters` 合同，统一输出 backlog 总量、各 asset_type 队列、优先级、滞留时长、推荐动作 | `src/api/research_utils.py`、`src/research/observe_philology.py` | `build_research_dashboard_payload()` 返回 `evidence_board.review_queue`，至少含 `total_pending`、`section_counts`、`priority_distribution` |
| H-1-2 | 扩展 research dashboard 查询参数与 schema，支持按 `asset_type`、`review_status`、`priority_bucket`、`reviewer` 过滤 review queue | `src/api/routes/research.py`、`src/api/schemas.py`、`src/api/research_utils.py` | `GET /api/research/jobs/{job_id}/dashboard` 可带以上过滤条件，返回的 `review_queue` 与 `review_workbench` 同步收敛 |
| H-1-3 | Web 控制台与服务端 dashboard 增加多选框、全选当前筛选结果、批量状态切换、批量备注填写，真正消费已有 batch endpoint | `web_console/static/index.html`、`src/web/routes/dashboard.py` | 用户可对当前可见卡片执行 1 次批量 accepted / rejected / needs_source / pending 写回，成功后刷新队列统计 |
| H-1-4 | `ResearchBatchPhilologyReviewRequest` 增加 `selection_snapshot` / `shared_decision_basis` / `shared_review_reasons` 等批处理审计字段，保证批量操作可回放 | `src/api/schemas.py`、`src/api/routes/research.py`、`src/research/review_workbench.py` | 批量写回 artifact 中能看到 selection snapshot 与共享备注，不丢失逐条覆盖字段 |

测试文件：

- `tests/unit/test_review_queue_contract.py`（新建，≥ 14 tests）
- `tests/test_research_utils.py`（追加 queue payload / filter contract / batch audit 字段断言）
- `tests/test_web_console_api.py`（追加批量文献学复核与 dashboard 过滤测试）
- `tests/unit/test_dashboard_copy.py`（追加多选工具条与批量动作文案渲染）

---

###### H-2 Reviewer 分配与负载视图

当前 reviewer 只是在写回时从 `auth_context` 或请求体里解析成字符串，仓储层并没有“谁正在处理哪些条目、每个人 backlog 多大、哪些条目无人认领”的结构化视图。要支撑真实研究积累，不能继续只靠 artifact 覆盖写回。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| H-2-1 | 新增 review task / assignment 结构化持久化模型，至少记录 `asset_type`、`asset_key`、`assignee`、`claimed_at`、`due_at`、`queue_status`、`priority_bucket` | `src/infrastructure/persistence.py`、`src/storage/db_models.py`、`alembic/versions/` | PG 中存在可查询的 review assignment 记录，不再只能从 artifact 反推当前负责人 |
| H-2-2 | `ResearchSessionRepository` 增加 claim / release / reassign / list_queue / aggregate_workload 等方法，统一承接 API 与 dashboard 查询 | `src/infrastructure/research_session_repo.py` | 仓储层可返回“未分配 / 已认领 / 已逾期”统计，以及按 reviewer 聚合的 pending / in_progress 数 |
| H-2-3 | API 补 reviewer 分配与负载接口，支持认领、转派、查看负载摘要 | `src/api/routes/research.py`、`src/api/schemas.py` | 存在可用的 assignment / workload 接口，返回 reviewer 维度的队列统计与最近处理记录 |
| H-2-4 | dashboard / web console 补 reviewer 负载看板与队列归属展示，至少显示“我负责”“无人认领”“超期项”三类视图 | `src/api/research_utils.py`、`src/web/routes/dashboard.py`、`web_console/static/index.html` | 前端可切换队列归属视图，且每张卡片显示当前 assignee / backlog age / priority |

测试文件：

- `tests/test_research_session_repo.py`（追加 assignment / workload 聚合测试）
- `tests/unit/test_reviewer_workload_board.py`（新建，≥ 10 tests）
- `tests/test_web_console_api.py`（追加 claim / reassign / workload API 测试）

---

###### H-3 争议归档与裁决流

当前 `decision_history` 只能保留被覆盖前的旧决策，适合审计，不足以表达“不同 reviewer 结论冲突”“等待资深裁决”“已完成争议归档”的工作流。Phase H 需要把争议从 audit trail 中显式抬出来。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| H-3-1 | 扩展 review contract：新增 `dispute_status`、`dispute_reason`、`resolution_status`、`adjudicator`、`superseded_by` 等字段，与 `review_status` 解耦 | `src/research/review_workbench.py`、`src/api/schemas.py` | 单条与批量 review payload 均可表达 dispute / resolve 状态，且兼容现有 4 类 `review_status` |
| H-3-2 | 新增 dispute archive 持久化与仓储接口，记录争议创建、升级、裁决、关闭全过程 | `src/infrastructure/persistence.py`、`src/infrastructure/research_session_repo.py`、`alembic/versions/` | 同一条目出现 reviewer 冲突时可形成 dispute case，并可按 case_id 查询历史 |
| H-3-3 | dashboard payload 增加 dispute inbox / dispute history 分组，工作台卡片显示 `decision_history` 与当前争议状态 | `src/api/research_utils.py`、`src/web/routes/dashboard.py`、`web_console/static/index.html` | 存在独立争议分组，用户可看到冲突前后决策链与当前待裁决项 |
| H-3-4 | API 增加争议升级与裁决入口，支持“标记争议”“指定裁决人”“裁决关闭”三步闭环 | `src/api/routes/research.py`、`src/api/schemas.py` | dispute case 可从待处理进入已裁决，裁决结果自动回写对应 workbench item |

测试文件：

- `tests/unit/test_review_dispute_contract.py`（新建，≥ 12 tests）
- `tests/test_research_pipeline_observe.py`（追加 decision_history / dispute 升级回归）
- `tests/test_workbench_evidence_chain.py`（追加 evidence_chain 争议与裁决测试）
- `tests/test_web_console_api.py`（追加 dispute inbox / resolve API 测试）

---

###### H-4 抽样质检与质量看板

当前已有 round-trip、dashboard payload、写回 artifact 的测试与实现，但缺少运营层面的抽样质检机制。没有采样计划、复核一致率和 overturn rate，就无法判断 review 效率提升是否牺牲了质量。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| H-4-1 | 新增 review sampling / QC 合同，支持按 reviewer、asset_type、review_status、priority 生成抽样计划与样本集 | `src/research/review_sampling.py`（新建）、`src/api/research_utils.py`、`src/research/observe_philology.py` | 可生成稳定的 sample set，至少输出 `sample_size`、`sampling_scope`、`sample_items` |
| H-4-2 | 持久化 QC 结果与质量指标，统计 `agreement_rate`、`overturn_rate`、`recheck_count`、`overdue_count`、`median_backlog_age_hours` | `src/infrastructure/persistence.py`、`src/infrastructure/research_session_repo.py`、`alembic/versions/` | QC 结果可按 cycle / reviewer / asset_type 查询，并返回聚合 summary |
| H-4-3 | API 与前端新增 `review_quality_summary` / sampling 操作面，展示抽检结果、待复检项和 reviewer 质量分布 | `src/api/routes/research.py`、`src/api/schemas.py`、`src/web/routes/dashboard.py`、`web_console/static/index.html` | dashboard 或独立 API 可返回 review quality summary，前端可触发抽样并查看结果 |
| H-4-4 | 架构回归守卫：dashboard payload 必须包含 `review_queue` 与 `review_quality_summary`，review workbench 批量流程不能退化回单条审核专用面 | `tests/unit/test_architecture_regression_guard.py`（新 Guard #38）、`src/api/research_utils.py`、`web_console/static/index.html` | Guard #38 在 queue / quality summary 丢失、批量工具条消失时直接失败 |

测试文件：

- `tests/unit/test_review_quality_sampling.py`（新建，≥ 12 tests）
- `tests/test_research_session_repo.py`（追加 QC 结果持久化与 summary 聚合测试）
- `tests/test_research_utils.py`（追加 `review_quality_summary` payload 测试）
- `tests/test_web_console_api.py`（追加 sampling / QC API 测试）

#### Phase I：小模型评测与默认策略化

- 目标：让 SmallModelOptimizer 从“可用基础设施”升级为“默认执行策略”。
- 动作：建立 phase benchmark、模板命中评测、budget 命中评测、fallback 质量评测。
- 理由：这一步决定本地 Qwen 能否长期稳定承担研究任务，而不是只在局部表现良好。
- 代价：中，约 1 周。

##### Phase I 可执行任务清单

> 建议按 I-1 -> I-2 -> I-3 -> I-4 顺序推进。I-1 先把默认执行路径真正接通，I-2 再建立可重复 benchmark 资产，I-3 / I-4 复用同一批 case 做模板、budget 与 fallback 质量评测。

---

###### I-1 SmallModelOptimizer 默认执行路径接线

当前 `get_small_model_optimizer()` 只是单例入口，`prepare_call()` 没有真实调用方；`reflect_phase`、`quality_assessor`、`experiment_designer`、`publish` 写作链仍保留直接 `generate()` 路径。若不先把默认规划层接通，后面的 benchmark 只能评估“未接线基础设施”。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| I-1-1 | 在 LLM 服务层新增统一规划 helper，把 `get_small_model_optimizer()`、`get_llm_service()`、token budget policy 串成单个调用入口，返回 `CallPlan` + 执行上下文 | `src/infra/llm_service.py`、`src/infra/small_model_optimizer.py` | 调用方无需自己拼 selector / strategy / compressor，统一 helper 可直接返回 plan 与实际 service |
| I-1-2 | hypothesis / analyze-quality / experiment design / reflect 的 LLM 入口全部先走 optimizer，再决定 `proceed` / `decompose` / `skip` / `retry_simplified` | `src/research/phases/hypothesis_phase.py`、`src/quality/quality_assessor.py`、`src/research/experiment_designer.py`、`src/research/phases/reflect_phase.py` | 目标入口均能产出 `CallPlan`；只有 `should_call_llm = true` 时才真正触发 generate |
| I-1-3 | publish 写作链接入按 section 规划的小模型执行面，paper writer 使用 dossier layer + framework metadata，而不是裸 prompt 直发 | `src/research/phases/publish_phase.py`、`src/generation/paper_writer.py`、`src/research/dossier_builder.py` | 论文生成结果里可看到 section 级 framework / layer / estimated_tokens 摘要 |
| I-1-4 | PhaseResult 补充统一 `small_model_plan`、`llm_cost_report`、`fallback_path` metadata，并新增回归守卫约束目标 phase 入口必须引用 optimizer | `src/research/phase_result.py`、`tests/unit/test_architecture_regression_guard.py`（新 Guard #39） | hypothesis / publish / reflect / experiment 相关结果含 optimizer metadata；Guard #39 在入口绕过 optimizer 时直接失败 |

测试文件：

- `tests/unit/test_small_model_optimizer_integration.py`（新建，≥ 14 tests）
- `tests/unit/test_publish_phase.py`（追加 section-level optimizer metadata 测试）
- `tests/unit/test_reflect_phase.py`、`tests/unit/test_reflect_phase_extended.py`（追加 planner / fallback metadata 测试）
- `tests/test_experiment_designer.py`、`tests/test_quality_assessor.py`、`tests/test_hypothesis_engine.py`（追加 optimizer 接线回归）

---

###### I-2 Phase benchmark 资产集与运行器

当前仓库只有 `tools/storage_stress_benchmark.py` 这类存储压测工具，以及 `test_cycle_system.py` / `test_full_cycle.py` 中的模拟性能分值；没有任何 SmallModelOptimizer 的 phase-level 评测资产和可重复运行器。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| I-2-1 | 新增本地 benchmark 运行器，支持对同一批 phase case 同时跑“优化路径”和“直接调用基线”，输出 JSON + Markdown 对照报告 | `tools/small_model_phase_benchmark.py`（新建）、`generate_test_report.py` | 运行器输出 per-phase 成本、动作分布、质量分，并可区分 optimized vs baseline |
| I-2-2 | 建立 Phase I 基准 case 资产，至少覆盖 hypothesis generation、analyze evidence synthesis、publish paper section、reflect diagnosis 四类任务 | `tests/fixtures/phase_i/hypothesis_cases.json`（新建）、`tests/fixtures/phase_i/analyze_cases.json`（新建）、`tests/fixtures/phase_i/publish_cases.json`（新建）、`tests/fixtures/phase_i/reflect_cases.json`（新建） | 每个 case 至少包含 dossier sections、expected_action、expected_framework、max_input_tokens、quality rubric |
| I-2-3 | 让 dossier builder / prompt registry 能导出 benchmark-ready 输入快照，保证 replay 输入稳定，不受运行期随机上下文影响 | `src/research/dossier_builder.py`、`src/infra/prompt_registry.py` | 同一 benchmark case 多次 replay 得到一致的 dossier snapshot 与 prompt 结构 |
| I-2-4 | 运行器输出 phase benchmark 汇总工件，沉淀到 output 目录，供后续 Phase D 学习闭环和人工审阅复用 | `tools/small_model_phase_benchmark.py`、`src/research/dossier_builder.py`、`output/` | 单次 benchmark 运行后生成可追溯的 phase summary、case diff、失败样例清单 |

测试文件：

- `tests/unit/test_small_model_phase_benchmark.py`（新建，≥ 12 tests）
- `tests/unit/test_dossier_builder.py`（追加 benchmark snapshot 稳定性测试）
- `tests/unit/test_reasoning_template_selector.py`（追加 benchmark expected framework 对照测试）

---

###### I-3 模板命中与 budget 命中评测

当前 `ReasoningTemplateSelector`、`DynamicInvocationStrategy`、token budget policy 都是独立正确的，但系统里没有“模板选得对不对”“预算裁剪是否命中预期”的实证统计，更没有把这些结果回灌给 `PolicyAdjuster.template_preferences`。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| I-3-1 | 扩展 `CallPlan` / cost telemetry，记录 `alternatives`、`budget_ratio`、`trimmed`、`cache_hit_likelihood`、`policy_source` 等评测字段 | `src/infra/small_model_optimizer.py`、`src/infra/dynamic_invocation_strategy.py`、`src/infra/llm_service.py` | 每次规划调用都能导出可比较 telemetry，不再只有 action / estimated_tokens |
| I-3-2 | benchmark 运行器增加 `template_hit_rate`、`budget_hit_rate`、`layer_hit_rate`、`decompose_rate`、`skip_rate` 统计，并按 phase 输出 | `tools/small_model_phase_benchmark.py`、`tests/fixtures/phase_i/*.json` | benchmark 报告中存在上述命中率，且能定位 miss 的具体 case |
| I-3-3 | 配置层新增 `models.llm.small_model_optimizer` 默认开关、phase overrides、目标命中率阈值，区分 development / production / test | `config.yml`、`config/production.yml`、`config/test.yml` | 生产环境可强制启用默认规划层；测试环境可固定阈值与 override，保证回归稳定 |
| I-3-4 | 学习闭环消费 benchmark summary，把模板命中与预算 miss 回灌为 `template_preferences` / `phase_thresholds` 调整信号 | `src/learning/policy_adjuster.py`、`src/research/learning_loop_orchestrator.py`、`tests/test_learning_governance_contract.py` | benchmark summary 能生成下一轮 template preference 调整建议，不再只凭 reflect 文本总结 |

测试文件：

- `tests/unit/test_token_budget_policy.py`（追加 budget hit / trim telemetry 测试）
- `tests/unit/test_llm_task_policy.py`（追加 phase task mapping 与 optimizer 联动测试）
- `tests/unit/test_reasoning_template_selector.py`（追加 template hit 评测断言）
- `tests/unit/test_small_model_optimizer_metrics.py`（新建，≥ 10 tests）
- `tests/test_learning_governance_contract.py`（追加 benchmark summary -> template preference 调整测试）

---

###### I-4 Fallback 质量评测与回归基线

`skip`、`decompose`、`retry_simplified` 和更下游的规则回退已经存在，但现在只能知道“动作被触发了”，不知道“触发后质量是否可接受”。如果没有 fallback 质量评测，默认策略化只会把经验判断自动化，而不是把质量边界制度化。

| 序号 | 任务 | 涉及文件 | 验收 |
| --- | --- | --- | --- |
| I-4-1 | 为 `skip` / `decompose` / `retry_simplified` / rules fallback 建立统一质量评测矩阵，比较 optimized path、baseline direct call、rule-only path 三者差异 | `tools/small_model_phase_benchmark.py`、`src/infra/dynamic_invocation_strategy.py`、`src/quality/quality_assessor.py` | benchmark 报告可输出 fallback 质量分、失败率、与 baseline 的差值 |
| I-4-2 | 目标 phase 结果补 `fallback_quality_score`、`fallback_acceptance`、`fallback_reason` 字段，用于后续 dashboard / learning 消费 | `src/research/phases/hypothesis_phase.py`、`src/research/phases/reflect_phase.py`、`src/research/phases/publish_phase.py`、`src/research/experiment_designer.py`、`src/quality/quality_assessor.py` | 发生 fallback 时 phase metadata 含质量分与接受/拒绝结论 |
| I-4-3 | 运行器导出 regression baseline，明确“优化路径至少不劣于 baseline direct call”的 phase-level 阈值 | `tools/small_model_phase_benchmark.py`、`generate_test_report.py` | 报告能直接给出 per-phase delta，且可配置最小可接受下降阈值 |
| I-4-4 | 新增回归守卫与专项测试，要求 optimizer benchmark baseline、fallback summary、phase metadata 长期存在 | `tests/unit/test_architecture_regression_guard.py`（新 Guard #40）、`tests/unit/test_small_model_fallback_quality.py`（新建） | Guard #40 在 benchmark baseline 字段、fallback summary 或目标 phase metadata 消失时直接失败 |

测试文件：

- `tests/unit/test_small_model_fallback_quality.py`（新建，≥ 12 tests）
- `tests/test_hypothesis_engine.py`（追加 fallback quality 回归）
- `tests/unit/test_publish_phase.py`、`tests/unit/test_reflect_phase.py`（追加 fallback metadata 与接受阈值测试）
- `tests/test_quality_assessor.py`（追加 fallback 质量对照测试）

---

### 9.3 Phase G / H / I 可直接建 Issue 的开发任务卡

> 使用方式：每张卡对应 1 个 issue / 1 条 PR 主线。标题可直接复制为 issue 标题，正文可直接复制为 issue 描述。建议建卡顺序保持 `G-1 -> G-4 -> H-1 -> H-4 -> I-1 -> I-4`，避免在同一张卡里混入多个子线。

| 卡片 | 建议标题 | 优先级 | 前置依赖 |
| --- | --- | --- | --- |
| G-1 | Phase G / G-1 建立 Neo4j schema versioning 与标签注册表 | P0 | 无 |
| G-2 | Phase G / G-2 假说与证据子图资产化 | P0 | G-1 |
| G-3 | Phase G / G-3 文献学子图治理 | P1 | G-1 |
| G-4 | Phase G / G-4 图回归检查与历史资产 backfill | P1 | G-2、G-3 |
| H-1 | Phase H / H-1 Review queue 与批量复核工作台 | P0 | 无 |
| H-2 | Phase H / H-2 Reviewer 分配与负载视图 | P1 | H-1 |
| H-3 | Phase H / H-3 争议归档与裁决流 | P1 | H-1、H-2 |
| H-4 | Phase H / H-4 抽样质检与质量看板 | P2 | H-1、H-2 |
| I-1 | Phase I / I-1 SmallModelOptimizer 默认执行路径接线 | P0 | 无 |
| I-2 | Phase I / I-2 建立 phase benchmark 资产集与运行器 | P1 | I-1 |
| I-3 | Phase I / I-3 模板命中与 budget 命中评测 | P1 | I-1、I-2 |
| I-4 | Phase I / I-4 Fallback 质量评测与回归基线 | P1 | I-1、I-2 |

---

###### Card G-1

当前状态：2026-04-21 已完成首轮落地，后续只保留 live E2E / backfill 联调到 G-4 一并收口。

- 建议标题：`Phase G / G-1 建立 Neo4j schema versioning 与标签注册表`
- 建议标签：`architecture`、`neo4j`、`graph-governance`、`phase-g`、`p0`
- 目标：把分散在图投影代码中的 schema 常量、标签、关系类型收口到单一 registry，并让 schema drift 变成可查询状态。
- 范围：
  - [x] 新建 `src/storage/graph_schema.py`，定义 `GRAPH_SCHEMA_VERSION`、标签、关系类型、属性白名单
  - [x] 在 `src/storage/neo4j_driver.py` 增加 schema bootstrap、`get_schema_version()`、`ensure_schema_version()`
  - [x] 让 `src/research/phase_orchestrator.py`、`src/research/research_session_graph_backfill.py` 改为通过 registry 取 label / relationship
  - [x] 在 `src/api/routes/analysis.py` 暴露 `schema_version`、`schema_drift_detected`
- 完成定义：
  - [x] 启用 Neo4j 后可读取 schema version，version mismatch 会给出 drift 报告
  - [x] session / phase / artifact / observe 投影不再直接硬编码标签与关系类型
- 测试：
  - [x] `tests/unit/test_graph_schema_versioning.py`
  - [x] `tests/unit/test_neo4j_driver.py`
  - [ ] `test_kg_e2e.py`（脚本已扩展，live API 尚未执行）

###### Card G-2

当前状态：2026-04-21 核心实现与全量回归已完成，剩余 live KG E2E 验证建议并入 G-4 资产级回归一起做。

- 建议标题：`Phase G / G-2 假说与证据子图资产化`
- 建议标签：`architecture`、`neo4j`、`knowledge-graph`、`phase-g`、`p0`
- 目标：把 hypothesis 与 evidence 从内存结果和 envelope 提升为可治理的图资产，而不是只停留在 phase payload。
- 范围：
  - [x] 在 `src/storage/graph_schema.py` 注册 `Hypothesis`、`Evidence`、`EvidenceClaim` 及核心关系类型
  - [x] 在 `src/research/phases/hypothesis_phase.py` 输出 `results["graph_assets"]["hypothesis_subgraph"]`
  - [x] 在 `src/research/phases/analyze_phase.py` 基于 `src/research/evidence_contract.py` 生成 evidence / claim 子图
  - [x] 由 `src/research/phase_orchestrator.py` 与 `src/storage/backend_factory.py` 统一承接图写入事务
- 完成定义：
  - [x] hypothesis_count > 0 时必有 hypothesis subgraph node / edge 统计
  - [x] 每条 claim 可回链到 evidence 节点，且图写入失败不会让 PG 事务误提交
- 测试：
  - [x] `tests/unit/test_graph_asset_subgraphs.py`
  - [x] `tests/unit/test_architecture_regression_guard.py`（Guard #36）
  - [ ] `test_kg_e2e.py`（脚本已扩展，live API 尚未执行）

###### Card G-3

当前状态：2026-04-21 已全部完成。

- 建议标题：`Phase G / G-3 文献学子图治理`
- 建议标签：`philology`、`neo4j`、`knowledge-graph`、`phase-g`、`p1`
- 目标：把 catalog / exegesis / fragment / textual evidence chain 变成稳定的 philology subgraph，供后续批量复核和图查询复用。
- 范围：
  - [x] 在 `src/storage/graph_schema.py` 注册 `Catalog`、`ExegesisTerm`、`FragmentCandidate`、`TextualEvidenceChain` 及其关系类型
  - [x] 让 `src/research/observe_philology.py`、`src/analysis/philology_service.py` 输出标准化 philology graph assets
  - [x] 把 `src/research/review_workbench.py` 的 `review_status`、`needs_manual_review`、`decision_basis` 同步进图节点属性
  - [x] 在 `tools/neo4j_query_templates.py` 与 `src/api/routes/analysis.py` 增加 philology asset graph 查询模板
- 完成定义：
  - [x] 存在 philology summary 时，可查询 `catalog -> witness -> fragment / exegesis` 链路
  - [x] 图节点属性可直接筛选 accepted / rejected / needs_source / pending
- 测试：
  - [x] `tests/unit/test_philology_graph_projection.py`
  - [x] `tests/unit/test_neo4j_query_governance.py`
  - [x] `tests/unit/test_textual_evidence_chain.py`
  - [x] `tests/unit/test_catalog_contract.py`

###### Card G-4

当前状态：2026-04-21 已全部完成。production-local preflight 预检输出：schema version=1.1.0（match）、projected nodes=703、edges=1393；`test_kg_e2e.py` live 端到端待在生产环境补跑。

- 建议标题：`Phase G / G-4 图回归检查与历史资产 backfill`
- 建议标签：`backfill`、`neo4j`、`regression`、`phase-g`、`p1`
- 目标：把新的图 schema 和子图模型固化为可回填、可回归、可预检的稳定基线。
- 范围：
  - [x] 扩展 `src/research/research_session_graph_backfill.py`，为旧 cycle 生成 schema v2 资产
  - [x] 为 `.vscode/production-local-backfill.ps1` 增加 graph schema version 与 dry-run 摘要
  - [x] 新增图回归守卫，覆盖 schema registry、核心标签计数、必备关系类型、KG stats 字段
  - [ ] 扩展 `test_kg_e2e.py`，验证 hypothesis / evidence / philology 三类资产级查询（脚本已扩展，live 跑待补）
- 完成定义：
  - [x] 旧 session 执行 backfill 后新增资产节点 / 边数量 > 0，且不破坏原有投影
  - [x] 预检输出可见 schema version、预计新增节点数、预计新增边数
- 测试：
  - [x] `tests/unit/test_graph_asset_regression.py`
  - [x] `tests/unit/test_architecture_regression_guard.py`（Guard #37）
  - [ ] `test_kg_e2e.py`（脚本已扩展，live API 尚未执行）

###### Card H-1

当前状态：2026-04-21 已全部完成，新增 18 个测试（`tests/unit/test_review_queue_contract.py`），全量单元套件 1234 passed。

- 建议标题：`Phase H / H-1 Review queue 与批量复核工作台`
- 建议标签：`philology`、`review-workbench`、`dashboard`、`phase-h`、`p0`
- 目标：把现有卡片式 review workbench 升级为显式 queue + batch workflow，而不是继续停留在单条审核视角。
- 范围：
  - [x] 在 `src/api/research_utils.py`、`src/research/observe_philology.py` 输出 `review_queue`、`queue_summary`、`queue_filters`
  - [x] 扩展 `src/api/routes/research.py`、`src/api/schemas.py`，支持按 `asset_type`、`review_status`、`priority_bucket`、`reviewer` 过滤 queue
  - [x] 让 `web_console/static/index.html` 与 `src/web/routes/dashboard.py` 支持多选、全选、批量状态切换、批量备注
  - [x] 为 `ResearchBatchPhilologyReviewRequest` 增加 `selection_snapshot`、共享备注与批处理审计字段
- 完成定义：
  - [x] dashboard payload 中存在可消费的 `review_queue` 与统计摘要
  - [x] 用户可对当前筛选结果执行一键批量 accepted / rejected / needs_source / pending 写回
- 测试：
  - [x] `tests/unit/test_review_queue_contract.py`
  - [x] `tests/test_research_utils.py`
  - [x] `tests/test_web_console_api.py`
  - [x] `tests/unit/test_dashboard_copy.py`

###### Card H-2

当前状态：2026-04-21 已全部完成，新增 31 个测试（12 仓储 + 12 看板契约 + 7 端点），核心子集 1385 passed。alembic migration revision `b5d8a91e3c47` 已就绪，需在生产环境执行 `alembic upgrade head`。

- 建议标题：`Phase H / H-2 Reviewer 分配与负载视图`
- 建议标签：`philology`、`assignment`、`dashboard`、`phase-h`、`p1`
- 目标：建立 reviewer assignment 事实面，解决“谁在处理什么、谁超载、哪些项无人认领”不可查询的问题。
- 范围：
  - [x] 在 `src/storage/db_models.py`、`src/infrastructure/persistence.py`、`alembic/versions/` 增加 review assignment 持久化模型（`ReviewAssignment` 表，UniqueConstraint + 4 索引）
  - [x] 在 `src/infrastructure/research_session_repo.py` 增加 claim / release / reassign / complete / list_queue / aggregate_workload
  - [x] 在 `src/api/routes/research.py`、`src/api/schemas.py` 增加 assignment / workload API（5 个端点 + 8 个 Pydantic 模型）
  - [x] 在 `src/api/research_utils.py`、`web_console/static/index.html` 增加“我负责 / 无人认领 / 超期项”三视图看板；`build_reviewer_workload_board()` 已接入 dashboard payload
- 完成定义：
  - [x] PG 中可查询 review assignment 记录，不再只能从 artifact 反推 assignee
  - [x] dashboard 卡片能展示 assignee、backlog age、priority
- 测试：
  - [x] `tests/test_research_session_repo.py`（`TestReviewAssignments` 12 例）
  - [x] `tests/unit/test_reviewer_workload_board.py`（新建，12 例契约测试）
  - [x] `tests/test_web_console_api.py`（`TestReviewAssignmentEndpoints` 7 例）

###### Card H-3

- 建议标题：`Phase H / H-3 争议归档与裁决流`
- 建议标签：`philology`、`dispute-resolution`、`review-workbench`、`phase-h`、`p1`
- 当前状态：2026-04-22 已全部完成，新增 34 个测试（15 仓储 + 12 看板契约 + 7 端点），核心子集 1419 passed。alembic migration revision `c7e9a32d8b54` 已就绪，需在生产环境执行 `alembic upgrade head` 创建 `review_disputes` 表。
- 目标：把 decision history 从审计线索升级为真实 dispute workflow，支持升级、裁决、关闭三步闭环。
- 范围：
  - [x] 在 `src/research/review_workbench.py`、`src/api/schemas.py` 增加 dispute / resolution 相关字段（H-3 在 schemas.py 新增 7 个 ReviewDispute* 模型）
  - [x] 在 `src/infrastructure/persistence.py`、`src/infrastructure/research_session_repo.py`、`alembic/versions/` 增加 dispute archive（新增 `ReviewDispute` ORM、6 个仓储方法、`c7e9a32d8b54_add_review_disputes_table.py`）
  - [x] 在 `src/api/research_utils.py`、`src/web/routes/dashboard.py`、`web_console/static/index.html` 增加 dispute inbox / history（新增 `build_dispute_archive_board`、dashboard 路由 thread `review_disputes`、UI 新增 `buildDisputeArchiveBoard` 三 tab：待处理/我裁决/历史）
  - [x] 在 `src/api/routes/research.py` 增加标记争议、指定裁决人、裁决关闭接口（5 个 endpoint：open/assign/resolve/withdraw/list）
- 完成定义：
  - [x] reviewer 冲突可形成 dispute case，并可按 case_id 查询完整历史
  - [x] 裁决关闭后，对应 workbench item 会自动回写最终状态（`resolve_review_dispute` 通过 `writeback_review_status` 调用 `upsert_observe_workbench_review_batch`）
- 测试：
  - [x] `tests/unit/test_review_dispute_contract.py`（12 通过）
  - [x] `tests/test_research_session_repo.py::TestReviewDisputes`（15 通过）
  - [x] `tests/test_web_console_api.py::TestReviewDisputeEndpoints`（7 通过）

###### Card H-4

- 建议标题：`Phase H / H-4 抽样质检与质量看板`
- 建议标签：`philology`、`quality-control`、`dashboard`、`phase-h`、`p2`
- 目标：建立 review sampling 与 QC summary，让批量复核效率提升不会以质量失控为代价。
- 当前状态：2026-04-22 已全部完成；新增 33 个测试（17 sampling 单测 + 3 repo + 2 utils + 5 endpoint + 6 Guard #38），核心子集 1452 通过 / 0 失败（H-3 基线为 1419）；本卡未引入 alembic migration（QC 指标全部基于 `review_assignments` + `review_disputes` 实时聚合）。
- 范围：
  - [x] 新建 `src/research/review_sampling.py`，支持按 reviewer / asset_type / review_status / priority 抽样
  - [x] 在持久化层与仓储层记录 `agreement_rate`、`overturn_rate`、`recheck_count`、`overdue_count`、`median_backlog_age_hours`
  - [x] 在 `src/api/routes/research.py`、`src/api/schemas.py`、`src/web/routes/dashboard.py`、`web_console/static/index.html` 增加 sampling 与 `review_quality_summary`
  - [x] 新增架构守卫，确保 queue / quality summary / batch toolbar 不被后续改动删掉
- 完成定义：
  - [x] 可生成稳定 sample set，并能按 cycle / reviewer / asset_type 返回 QC summary
  - [x] dashboard 或独立 API 能展示 review quality summary 并触发抽样
- 测试：
  - [x] `tests/unit/test_review_quality_sampling.py`（17 通过）
  - [x] `tests/test_research_session_repo.py::TestReviewQualitySummaryRepo`（3 通过）
  - [x] `tests/test_research_utils.py`（2 个 H-4 propagation 测试通过）
  - [x] `tests/test_web_console_api.py::TestReviewQualityAndSamplingEndpoints`（5 通过）
  - [x] `tests/unit/test_architecture_regression_guard.py::TestGuard38_ReviewQualityToolbar`（6 通过）

###### Card I-1

- 建议标题：`Phase I / I-1 SmallModelOptimizer 默认执行路径接线`
- 建议标签：`llm`、`optimizer`、`runtime`、`phase-i`、`p0`
- 目标：让 optimizer 从“基础设施入口”变成默认规划层，杜绝关键 phase 继续裸调 `generate()`。
- 范围：
  - [ ] 在 `src/infra/llm_service.py`、`src/infra/small_model_optimizer.py` 新增统一规划 helper
  - [ ] 让 `src/research/phases/hypothesis_phase.py`、`src/quality/quality_assessor.py`、`src/research/experiment_designer.py`、`src/research/phases/reflect_phase.py` 全部先走 optimizer
  - [ ] 让 `src/research/phases/publish_phase.py`、`src/generation/paper_writer.py` 基于 section 级 plan 消费 dossier layer 与 framework metadata
  - [ ] 在 `src/research/phase_result.py` 增加 `small_model_plan`、`llm_cost_report`、`fallback_path` metadata，并新增 Guard #39
- 完成定义：
  - [ ] 目标 phase 只有在 `should_call_llm = true` 时才真正触发 generate
  - [ ] hypothesis / publish / reflect / experiment 结果都能看到 optimizer metadata
- 测试：
  - [ ] `tests/unit/test_small_model_optimizer_integration.py`
  - [ ] `tests/unit/test_publish_phase.py`
  - [ ] `tests/unit/test_reflect_phase.py`
  - [ ] `tests/unit/test_reflect_phase_extended.py`
  - [ ] `tests/test_experiment_designer.py`
  - [ ] `tests/test_quality_assessor.py`
  - [ ] `tests/test_hypothesis_engine.py`

###### Card I-2

- 建议标题：`Phase I / I-2 建立 phase benchmark 资产集与运行器`
- 建议标签：`llm`、`benchmark`、`evaluation`、`phase-i`、`p1`
- 目标：建立一套可重复 replay 的 phase benchmark，比较优化路径与直接调用基线，而不是只凭体感判断优化效果。
- 当前状态：2026-04-22 已全部完成；benchmark 工具 + 4 个 phase fixture + 3 个测试文件都在位，本轮补齐 dossier_builder / prompt_registry 的 benchmark-ready snapshot 导出、benchmark 报告增加 `failed_cases` 与 `prompt_registry_snapshot`；新增 12 个测试（49 逻辑在本卡范围内通过），核心子集 1464 通过 / 0 失败。
- 范围：
  - [x] 新建 `tools/small_model_phase_benchmark.py`，输出 JSON + Markdown 对照报告
  - [x] 新建 `tests/fixtures/phase_i/` 下的 hypothesis / analyze / publish / reflect case 资产
  - [x] 让 `src/research/dossier_builder.py`、`src/infra/prompt_registry.py` 能导出 benchmark-ready 输入快照（`build_benchmark_input_snapshot` / `export_prompt_registry_snapshot`）
  - [x] 让 benchmark 输出沉淀到 `output/phase_benchmarks/`，供学习闭环与人工复核复用
- 完成定义：
  - [x] 单次运行后能拿到 per-phase 成本、动作分布、质量分、case diff、失败样例（`failed_cases` 按 phase 汇总）
  - [x] 同一 case 多次 replay 得到一致 dossier snapshot 与 prompt 结构（sha256 fingerprint 希望完全一致）
- 测试：
  - [x] `tests/unit/test_small_model_phase_benchmark.py`（8 通过，含 4 个 I-2 新增 replay/快照/失败样例用例）
  - [x] `tests/unit/test_dossier_builder.py::TestBenchmarkInputSnapshot`（5 通过）
  - [x] `tests/unit/test_reasoning_template_selector.py::TestPhaseIBenchmarkReplay`（3 通过）

###### Card I-3

- 建议标题：`Phase I / I-3 模板命中与 budget 命中评测`
- 建议标签：`llm`、`benchmark`、`token-budget`、`phase-i`、`p1`
- 目标：把 template selection、budget policy、layer compression 的命中效果做成可度量指标，并回灌给学习闭环。
- 范围：
  - [ ] 扩展 `src/infra/small_model_optimizer.py`、`src/infra/dynamic_invocation_strategy.py`、`src/infra/llm_service.py` 的 telemetry 字段
  - [ ] 扩展 `tools/small_model_phase_benchmark.py`，输出 `template_hit_rate`、`budget_hit_rate`、`layer_hit_rate`、`decompose_rate`、`skip_rate`
  - [ ] 在 `config.yml`、`config/production.yml`、`config/test.yml` 增加 `models.llm.small_model_optimizer` 默认开关与阈值
  - [ ] 让 `src/learning/policy_adjuster.py`、`src/research/learning_loop_orchestrator.py` 消费 benchmark summary
- 完成定义：
  - [ ] benchmark 报告可按 phase 输出命中率，并定位 miss case
  - [ ] benchmark summary 能生成下一轮 `template_preferences` / `phase_thresholds` 调整建议
- 测试：
  - [ ] `tests/unit/test_token_budget_policy.py`
  - [ ] `tests/unit/test_llm_task_policy.py`
  - [ ] `tests/unit/test_reasoning_template_selector.py`
  - [ ] `tests/unit/test_small_model_optimizer_metrics.py`
  - [ ] `tests/test_learning_governance_contract.py`

###### Card I-4

- 建议标题：`Phase I / I-4 Fallback 质量评测与回归基线`
- 建议标签：`llm`、`fallback`、`benchmark`、`phase-i`、`p1`
- 目标：把 `skip` / `decompose` / `retry_simplified` / rules fallback 的质量边界制度化，避免默认策略化后只知道动作触发、不知道质量是否可接受。
- 范围：
  - [ ] 在 `tools/small_model_phase_benchmark.py`、`src/infra/dynamic_invocation_strategy.py`、`src/quality/quality_assessor.py` 建立 fallback 质量矩阵
  - [ ] 为 `src/research/phases/hypothesis_phase.py`、`src/research/phases/reflect_phase.py`、`src/research/phases/publish_phase.py`、`src/research/experiment_designer.py`、`src/quality/quality_assessor.py` 增加 fallback 质量元数据
  - [ ] 导出 regression baseline，明确“优化路径至少不劣于 direct-call baseline”的 phase 阈值
  - [ ] 新增 Guard #40 与专项测试，锁定 benchmark baseline、fallback summary、phase metadata
- 完成定义：
  - [ ] benchmark 报告可输出 fallback 质量分、失败率、与 baseline 的 delta
  - [ ] 发生 fallback 时 phase metadata 含 `fallback_quality_score`、`fallback_acceptance`、`fallback_reason`
- 测试：
  - [ ] `tests/unit/test_small_model_fallback_quality.py`
  - [ ] `tests/test_hypothesis_engine.py`
  - [ ] `tests/unit/test_publish_phase.py`
  - [ ] `tests/unit/test_reflect_phase.py`
  - [ ] `tests/test_quality_assessor.py`

---

## 附录 A：2026-04-21 代码质量治理推进摘要

### 测试基线变化

| 指标 | 审计起点 (04-20) | 当前 (04-21) | 变化 |
| --- | --- | --- | --- |
| passed | 2893 | 3046 | +153（含 Phase F/G/I 新增测试） |
| failed | 1 (cypher injection scan) | 0 | 已修复 |
| xfailed | 4 | 4 | 不变 |
| skipped | 2 | 2 | 不变 |
| warnings | 240 | 175 | -65（pyproject.toml filterwarnings 生效） |

**G-3/G-4/H-1/H-2 推进后（2026-04-21 末）：**

| 指标 | 04-21 早 (G-2 后，unit 套件) | 04-21 末 (H-2 后，核心子集) | 变化 |
| --- | --- | --- | --- |
| passed（核心子集） | ~1216（unit 套件） | 1385 | +169（G-3/G-4/H-1/H-2 新增） |
| failed | 0 | 0 | 不变 |
| 新增测试（单阶段） | — | H-1: 18 / H-2: 31 | G-3/G-4 主要是守卫扩展 |

### 本次修复项

| 问题 | 修复文件 | 说明 |
| --- | --- | --- |
| production.yml 重复 `web_console:` 键 | `config/production.yml` | 合并两个同名块为单一块 |
| Pylance extraPaths 缺少项目根 | `.vscode/settings.json` | 增加 `"."` 到 `python.analysis.extraPaths` |
| cycle_reporter.py 未被识别的 re-export | `src/cycle/cycle_reporter.py` | 改用 `X as X` 惯用法 |
| test_config_loader tearDown Windows PermissionError | `tests/test_config_loader.py` | 增加 `gc.collect()` + try/except |
| Cypher injection scan 误报 | `src/storage/neo4j_driver.py` | 内联 `_safe_cypher_label()` 到 f-string |
| Neo4jDriver shutdown 资源泄漏 | `src/api/app.py`、`web_console/app.py` | shutdown 中 `factory.close()` + `unbind` |
| 第三方 DeprecationWarning 噪音 | `pyproject.toml` | 新增 7 条 filterwarnings |
| Neo4j schema versioning 与标签注册表 | `src/storage/graph_schema.py`、`src/storage/neo4j_driver.py`、`src/api/routes/analysis.py` | G-1 完成 schema registry、drift 检查与 KG stats 输出 |
| hypothesis / evidence graph assets 首轮资产化 | `src/research/graph_assets.py`、`src/research/phases/hypothesis_phase.py`、`src/research/phases/analyze_phase.py`、`src/research/phase_orchestrator.py` | G-2 完成子图构建、统一事务投影、graph_report 计数 |

### Phase G-3 / G-4 / H-1 / H-2 / H-3 / H-4 状态更新（2026-04-22）

Phase G-3（文献学子图治理）已**全部完成**：

- [x] G-3-1：schema registry 已注册 `Catalog`、`ExegesisTerm`、`FragmentCandidate`、`TextualEvidenceChain` 等节点及关系类型 ✓
- [x] G-3-2：`observe_philology` / `philology_service` 已输出标准化 philology graph assets，与 `VersionLineage` / `VersionWitness` 节点打通 ✓
- [x] G-3-3：`review_status`、`needs_manual_review`、`decision_basis` 已同步进图节点属性 ✓
- [x] G-3-4：文献学子图查询模板已补充，`/api/analysis/kg/subgraph` 支持 philology graph_type ✓

Phase G-4（图回归检查与历史资产 backfill）已**全部完成**（除 live E2E）：

- [x] G-4-1：`research_session_graph_backfill` 已扩展 schema v2 hypothesis / evidence / philology 资产 backfill ✓
- [x] G-4-2：`.vscode/production-local-backfill.ps1` 已增加 schema version 参数与 dry-run 摘要（projected nodes=703、edges=1393）✓
- [x] G-4-3：图回归守卫 Guard #37 已新增 ✓
- [ ] G-4-4：`test_kg_e2e.py` 脚本已扩展，live API 尚未执行一次完整端到端跑

Phase H-1（Review queue 与批量复核工作台）已**全部完成**：

- [x] H-1-1：`build_research_dashboard_payload()` 已输出 `evidence_board.review_queue`，含 `total_pending`、`section_counts`、`priority_distribution` ✓
- [x] H-1-2：`GET /api/research/jobs/{job_id}/dashboard` 可带 `asset_type`、`review_status`、`priority_bucket`、`reviewer` 过滤 ✓
- [x] H-1-3：web console 已支持多选、全选、批量状态切换、批量备注，已消费 batch endpoint ✓
- [x] H-1-4：`ResearchBatchPhilologyReviewRequest` 已增加 `selection_snapshot`、`shared_decision_basis`、`shared_review_reasons` 等审计字段 ✓

Phase H-2（Reviewer 分配与负载视图）已**全部完成**：

- [x] H-2-1：`ReviewAssignment` ORM 模型已新增（UniqueConstraint + 4 索引），alembic migration `b5d8a91e3c47` 已就绪 ✓
- [x] H-2-2：`ResearchSessionRepository` 已增加 claim / release / reassign / complete / list_review_queue / aggregate_reviewer_workload ✓
- [x] H-2-3：5 个新 API 端点 + 8 个 Pydantic 模型已上线 ✓
- [x] H-2-4：`build_reviewer_workload_board()` 已接入 dashboard payload；web console 已增加"我负责 / 无人认领 / 超期项"三 tab 看板 ✓

Phase H-3（争议归档与裁决流）已**全部完成**：

- [x] H-3-1：`ReviewDispute` ORM 模型已新增（UniqueConstraint(cycle_id, case_id) + 4 索引），alembic migration `c7e9a32d8b54` 已就绪 ✓
- [x] H-3-2：`ResearchSessionRepository` 已增加 open / assign / resolve / withdraw / list_review_disputes / get_review_dispute（含 `_generate_dispute_case_id` / `_append_dispute_event` 帮手）✓
- [x] H-3-3：5 个新 API 端点 + 7 个 Pydantic 模型已上线（POST open/assign/resolve/withdraw + GET list）✓
- [x] H-3-4：`build_dispute_archive_board()` 已接入 dashboard payload；`resolve_review_dispute` 通过 `writeback_review_status` 自动回写 workbench 终态；web console 已增加"待处理 / 我裁决 / 历史"三 tab 看板 ✓

Phase H-4（抽样质检与质量看板）已**全部完成**：

- [x] H-4-1：新建 `src/research/review_sampling.py`，导出 `build_review_sample`（按 reviewer/asset_type/review_status/priority 过滤 + 基于 sha256 的稳定排序 + seed 去随机化）与 `compute_review_quality_summary`（agreement_rate / overturn_rate / recheck_count / overdue_count / median_backlog_age_hours，repo `assignee` 与测试 `reviewer` 字段双兼容）✓
- [x] H-4-2：`ResearchSessionRepository.aggregate_review_quality_summary(cycle_id, reviewer, asset_type, now)` 已新增，复用 `list_review_queue` + `list_review_disputes` 实时聚合，无需新表 / 无 alembic migration ✓
- [x] H-4-3：`POST /api/research/sessions/{cycle_id}/review-sample` 与 `GET /api/research/sessions/{cycle_id}/review-quality-summary` 端点 + 5 个 Pydantic 模型（`ReviewSampleRequest/Summary/Response`、`ReviewQualitySummary/Response`）已上线；dashboard payload 与 `evidence_board.review_quality_summary` 已联通；web console 已新增 `buildReviewQualitySummary` 工具区 ✓
- [x] H-4-4：Guard #38 已新增（6 个断言：sampling 模块符号 / repo 聚合方法 / dashboard payload 字段 / H-1~H-4 端点路径 / web console review 工具条函数 / Pydantic schema 指标字段）✓

### Phase G-1 / G-2 状态更新

Phase G-1（Neo4j schema versioning 与标签注册表）在 2026-04-21 已**全部完成**：

- [x] G-1-1：`src/storage/graph_schema.py` 已建立 schema registry、标签注册表与属性白名单 ✓
- [x] G-1-2：`src/storage/neo4j_driver.py` 已具备 schema bootstrap、`get_schema_version()`、`ensure_schema_version()` ✓
- [x] G-1-3：`phase_orchestrator` / `research_session_graph_backfill` / `neo4j_driver` 已统一走 registry helper ✓
- [x] G-1-4：`/api/analysis/kg/stats` 已输出 `schema_version`、`schema_drift_detected` 与 graph statistics ✓

Phase G-2（假说 / 证据子图资产化）在 2026-04-21 已**完成首轮落地并通过全量回归**：

- [x] G-2-1：schema registry 已注册 `Hypothesis`、`Evidence`、`EvidenceClaim` 及核心关系类型 ✓
- [x] G-2-2：`hypothesis_phase` 已输出 `results["graph_assets"]["hypothesis_subgraph"]` ✓
- [x] G-2-3：`analyze_phase` 已基于 `EvidenceEnvelope` 输出 `evidence_subgraph`，claim 可回链 evidence ✓
- [x] G-2-4：主持久化路径已统一承接 hypothesis / evidence 图写入，图写失败不会放行 PG 提交 ✓
- [ ] `test_kg_e2e.py` 已扩展 graph asset 输出，但尚未对 live API 完成一次端到端验证

### Phase F-4 状态更新

Phase F-4（Known-failure 白名单机制）在本文写作时已**全部完成**：

- [x] F-4-1：pyproject.toml 注册 `known_failure` 自定义 marker ✓
- [x] F-4-2：为 4 个已知失败添加 `@pytest.mark.xfail` ✓
- [x] F-4-3：`tests/conftest.py` 已存在，含 `--strict-known-failures` 选项 ✓
- [x] F-4-4：回归基线已文档化于此（3046 pass / 4 xfail / 2 skip）✓

### Phase I-1 部分推进

SmallModelOptimizer planner 已与 hypothesis / reflect / quality / experiment / publish 五阶段接线完成（详见 `src/infra/small_model_optimizer.py` 单例入口与各 phase 调用路径），回归守卫已在位。

### 继续推进建议

从本文档任意一天恢复工作时，建议按以下顺序：

1. 运行核心子集回归确认基线：`.\venv310\Scripts\Activate.ps1; python -m pytest tests/unit tests/test_research_session_repo.py tests/test_research_utils.py tests/test_web_console_api.py -q --disable-warnings`
2. 确认 1464 passed / 0 failed（含 H-2 31 个 + H-3 34 个 + H-4 33 个 + I-2 12 个新增用例）
3. 生产环境执行 `alembic upgrade head` 创建 `review_disputes` 表（migration `c7e9a32d8b54`，down_revision `b5d8a91e3c47`）；H-4 / I-2 不引入新 migration
4. 如需补验证面，执行 `test_kg_e2e.py` 对 live `/api/analysis/kg/stats` 与 graph asset 输出做一次端到端确认
5. 按 **Phase I-3** 顺序继续推进

---

## 10. 最终判断

截至 2026-04-20，这套系统最准确的定位是：

“一套本地部署、以中医文献研究法为核心约束、具备七阶段科研主链、结构化资产沉淀、文献学工作台、自学习闭环和小模型成本治理能力的中医文献研究平台雏形。”

它已经明显超过“脚本拼装”阶段，也已经超过“普通 RAG 应用”阶段。当前剩余工作不再是补一个缺失功能，而是把已经形成的边界、协议、图谱治理和评测体系继续做厚。换句话说，现在最重要的不是重写，而是稳态化。

如果只能给出一句结论，那就是：

这套架构已经值得继续沿当前方向推进，且下一阶段应优先做治理深化，而不是做新的大范围功能扩张。
