# 中医古文献研究系统 — 架构设计文档 v2.0

> **分支**: `stage2-s2_1-preprocessor-opt`
> **日期**: 2026-04-21
> **版本**: 2.0.0

---

## 目录

1. [系统架构概览](#1-系统架构概览)
2. [中医文献研究法实现矩阵](#2-中医文献研究法实现矩阵)
3. [研究主流程图](#3-研究主流程图)
4. [数据流时序图](#4-数据流时序图)
5. [TCM 知识图谱本体模型](#5-tcm-知识图谱本体模型)
6. [模块依赖关系图](#6-模块依赖关系图)
7. [技术债务分析](#7-技术债务分析)
8. [分阶段实施计划](#8-分阶段实施计划)

---

## 1. 系统架构概览

本系统是一套面向中医古文献研究的全自动 AI 科研平台，核心功能包括：
- 多源文献检索与采集（CText、PubMed、arXiv、本地语料）
- 中医古文献专项预处理（繁简转换、异体字规范、古籍元数据提取）
- 六种中医文献研究方法（文献梳理/计量/校勘/训诂/版本对勘/综合研究）
- 本地 Qwen 1.5-7B 模型驱动的智能科研辅助
- Neo4j 知识图谱 + PostgreSQL + ChromaDB 三层持久化
- 自我学习闭环（研究结果→知识更新→RAG 增强）

### 1.1 系统部署图

```mermaid
graph TB
    subgraph 用户层
        U1[Web Console<br/>FastAPI + WebSocket]
        U2[REST API<br/>src/api/]
        U3[命令行<br/>run_cycle_demo.py]
    end

    subgraph 业务层
        R1[TCMResearchFlow<br/>六阶段研究主流程]
        R2[ResearchPipeline<br/>科研周期管理]
        R3[ResearchMethodRouter<br/>15种研究方法路由]
        R4[LLMResearchAdvisor<br/>AI科研顾问]
        R5[RAGService<br/>HyDE + Self-RAG]
    end

    subgraph AI层
        L1[LLMGateway<br/>统一 LLM 调用]
        L2[Qwen1.5-7B-Chat<br/>本地 GGUF 模型]
        L3[RAPTORIndexer<br/>分层文本索引]
    end

    subgraph 数据处理层
        D1[DocumentPreprocessor<br/>古籍预处理+元数据]
        D2[AdvancedEntityExtractor<br/>实体抽取]
        D3[SemanticGraphBuilder<br/>语义图构建]
        D4[TCMKnowledgeUpdater<br/>知识自更新]
    end

    subgraph 存储层
        S1[(Neo4j<br/>知识图谱)]
        S2[(PostgreSQL<br/>结构化数据)]
        S3[(ChromaDB<br/>向量检索)]
    end

    U1 & U2 & U3 --> R1 & R2
    R1 --> R3 & R4 & R5
    R4 & R5 --> L1
    L1 --> L2
    R5 --> L3
    R1 & R2 --> D1 & D2 & D3
    D4 --> S1 & S2 & S3
    R1 --> D4
    D3 --> S1
```

---

## 2. 中医文献研究法实现矩阵

| 研究方法 | 路由键 | 模块位置 | 实现状态 | 核心功能 |
|---------|-------|---------|---------|---------|
| 文献梳理法 | `tcm_literature_sorting` | `src/research/tcm_literature_methods.py` | ✅ 已实现 | 朝代分组、主题提取、演变脉络 |
| 文献计量法 | `tcm_bibliometrics` | `src/research/tcm_literature_methods.py` | ✅ 已实现 | 词频统计、共现网络、种子词分析 |
| 古籍校勘法 | `tcm_textual_criticism` | `src/research/tcm_literature_methods.py` | ✅ 已实现 | 异文检测、版本差异、校勘摘要 |
| 训诂学方法 | `tcm_exegesis` | `src/research/tcm_literature_methods.py` | ✅ 已实现 | 术语识别、语义注释、候选扩充 |
| 版本对勘法 | `tcm_version_collation` | `src/research/tcm_literature_methods.py` | ✅ 已实现 | Jaccard 相似度、谱系构建、底本建议 |
| 综合研究法 | `tcm_integrated_literature` | `src/research/tcm_literature_methods.py` | ✅ 已实现 | 多方法汇总、研究空白识别 |
| 方剂结构分析 | `formula_structure` | `src/semantic_modeling/methods/formula_structure.py` | ✅ 已实现 | 君臣佐使配伍分析 |
| 方剂比较 | `formula_comparator` | `src/semantic_modeling/methods/formula_comparator.py` | ✅ 已实现 | 方剂相似度比较 |
| 网络药理学 | `network_pharmacology` | `src/semantic_modeling/methods/network_pharmacology.py` | ✅ 已实现 | 靶点网络分析 |
| 古典文献考古 | `classical_literature` | `src/semantic_modeling/methods/classical_literature.py` | ✅ 已实现 | 知识考古与文献溯源 |
| Meta 分析 | `meta_analysis` | `src/semantic_modeling/methods/meta_analysis.py` | ✅ 已实现 | 异质性检验、效应量合并 |
| 复杂性科学 | `complexity_dynamics` | `src/semantic_modeling/methods/complexity_science.py` | ✅ 已实现 | 非线性动力学分析 |
| 综合集成 | `integrated_research` | `src/semantic_modeling/methods/integrated_analyzer.py` | ✅ 已实现 | 多维度整合分析 |

---

## 3. 研究主流程图

```mermaid
flowchart TD
    START([🔬 研究课题输入]) --> P1

    subgraph P1["阶段1：课题立项"]
        P1A[Qwen LLM 分析\n研究意义与目标] --> P1B[确定研究方法组合]
        P1B --> P1C[规划文献收集范围]
    end

    subgraph P2["阶段2：文献收集"]
        P2A[CText 古籍数据库] --> P2D[语料汇总]
        P2B[本地语料库] --> P2D
        P2C[PubMed/arXiv] --> P2D
        P2D --> P2E[文献质量筛选]
    end

    subgraph P3["阶段3：文献整理"]
        P3A[DocumentPreprocessor\n繁简转换+异体字规范] --> P3B
        P3B[古籍元数据提取\n朝代/作者/类型] --> P3C
        P3C[注疏识别与标注] --> P3D[结构化语料库]
    end

    subgraph P4["阶段4：文献分析"]
        P4A[文献梳理法\n朝代脉络] --> P4G
        P4B[文献计量法\n词频网络] --> P4G
        P4C[古籍校勘法\n异文比对] --> P4G
        P4D[训诂学方法\n术语解读] --> P4G
        P4E[版本对勘法\n底本选取] --> P4G
        P4F[综合研究法\n多法汇总] --> P4G
        P4G[Qwen LLM 学术解读] --> P4H[分析报告]
    end

    subgraph P5["阶段5：综合研究"]
        P5A[RAGService HyDE\n知识检索增强] --> P5C
        P5B[KG 推理\nNeo4j 图查询] --> P5C
        P5C[Qwen LLM\n综合结论生成] --> P5D[核心研究发现]
    end

    subgraph P6["阶段6：成果输出"]
        P6A[IMRD 格式报告] --> P6C
        P6B[Markdown/DOCX/JSON] --> P6C
        P6C[TCMKnowledgeUpdater\n知识图谱更新] --> P6D[(Neo4j + ChromaDB\n知识持久化)]
    end

    P1 --> P2 --> P3 --> P4 --> P5 --> P6 --> END([📄 研究报告 + 知识更新])

    P6D -.->|自学习反馈| P5A
```

---

## 4. 数据流时序图

```mermaid
sequenceDiagram
    participant U as 用户/API
    participant F as TCMResearchFlow
    participant PP as DocumentPreprocessor
    participant MR as ResearchMethodRouter
    participant LLM as LLMGateway(Qwen)
    participant RAG as RAGService
    participant KU as TCMKnowledgeUpdater
    participant DB as StorageGateway

    U->>F: run(topic, corpus)
    F->>LLM: 课题立项分析(Phase1 prompt)
    LLM-->>F: 研究方案文本

    F->>DB: 查询历史语料
    DB-->>F: 相关文献

    F->>PP: execute({raw_text})
    PP->>PP: 繁简转换 + 异体字规范化
    PP->>PP: extract_tcm_document_metadata()
    PP-->>F: 处理后文档 + TCM 元数据

    loop 每种文献研究方法
        F->>MR: route(tcm_method, corpus)
        MR-->>F: 分析结果 dict
    end

    F->>LLM: 文献分析解读(Phase4 prompt)
    LLM-->>F: 学术解读文本

    F->>RAG: retrieve(topic, use_hyde=True)
    RAG->>LLM: HyDE 假设文档生成
    LLM-->>RAG: 假设文档向量
    RAG-->>F: 相关文献片段

    F->>LLM: 综合研究结论(Phase5 prompt)
    LLM-->>F: 核心研究结论

    F->>LLM: IMRD 报告生成(Phase6 prompt)
    LLM-->>F: 结构化报告

    F->>KU: update_from_research_result(result)
    KU->>DB: save_entities(herbs, formulas...)
    KU->>DB: save_relations(contains, treats...)
    KU->>RAG: index_documents(texts)
    DB-->>KU: 写入确认
    KU-->>F: UpdateStats

    F-->>U: TCMResearchResult(report, phases, stats)
```

---

## 5. TCM 知识图谱本体模型

```mermaid
classDiagram
    class Corpus {
        +String corpus_id
        +String title
        +String dynasty
        +String author
        +String text_type
        +String source_url
        +analyzeMetadata()
    }

    class Formula {
        +String formula_id
        +String name
        +String source_book
        +String dynasty
        +String[] indications
        +String composition_principle
        +compareTo(other)
    }

    class Herb {
        +String herb_id
        +String name
        +String[] properties
        +String[] meridians
        +String[] effects
        +String toxicity
    }

    class Effect {
        +String effect_id
        +String name
        +String category
        +String[] target_organs
    }

    class Syndrome {
        +String syndrome_id
        +String name
        +String[] symptoms
        +String pathogenesis
        +String treatment_principle
    }

    class Disease {
        +String disease_id
        +String name
        +String tcm_category
        +String western_equivalent
    }

    Corpus "1" --> "n" Formula : 收录(CONTAINS)
    Formula "1" --> "n" Herb : 组成(COMPOSED_OF)
    Herb "1" --> "n" Effect : 具有(HAS_EFFECT)
    Formula "1" --> "n" Syndrome : 主治(TREATS_SYNDROME)
    Syndrome "n" --> "1" Disease : 属于(BELONGS_TO)
    Formula "n" --> "n" Formula : 演变自(EVOLVED_FROM)
    Corpus "n" --> "n" Corpus : 引用(CITES)
```

---

## 6. 模块依赖关系图

```mermaid
graph LR
    subgraph 入口层
        A1[run_cycle_demo.py]
        A2[src/api/app.py]
        A3[src/web/main.py]
    end

    subgraph 研究编排层
        B1[TCMResearchFlow]
        B2[ResearchPipeline]
        B3[ResearchMethodRouter]
    end

    subgraph 文献研究方法层
        C1[tcm_literature_methods\n6种TCM文献研究法]
        C2[semantic_modeling/methods\n11种语义建模方法]
        C3[LLMResearchAdvisor]
    end

    subgraph 数据处理层
        D1[DocumentPreprocessor\n古籍专项增强]
        D2[AdvancedEntityExtractor]
        D3[SemanticGraphBuilder]
    end

    subgraph 学习层
        E1[RAGService\nHyDE+Self-RAG]
        E2[RAPTORIndexer\n分层索引]
        E3[TCMKnowledgeUpdater\n知识自更新]
        E4[SelfLearningEngine]
    end

    subgraph 基础设施层
        F1[LLMGateway\nQwen1.5-7B]
        F2[StorageGateway\nNeo4j+PG+Chroma]
        F3[EventBus]
        F4[ModuleFactory]
    end

    A1 & A2 & A3 --> B1 & B2
    B1 --> B3 & C3 & E3
    B2 --> B3
    B3 --> C1 & C2
    B1 --> D1 & D2 & D3
    E1 & E2 & E3 --> F1 & F2
    C3 --> F1
    D1 --> F1
    B2 --> F3 & F4
```

---

## 7. 技术债务分析

### 7.1 高优先级债务（阻断性）

| ID | 问题 | 影响 | 建议解决方案 |
|----|------|------|------------|
| TD-01 | `src/preprocessor/` 与 `src/analysis/preprocessor.py` 双重路径 | 导入混乱，警告噪音 | 完全删除旧 `src/preprocessor/` 包，统一用 `src/analysis/preprocessor` |
| TD-02 | `src/infra/` 与 `src/infrastructure/` 两套基础设施包 | 重复代码，维护困难 | 已有 infra 重定向，需清理 `src/infra/` 旧文件 |
| TD-03 | jieba 依赖在 CI 环境缺失导致 95 个测试失败 | CI 不稳定 | 将 jieba 加入 CI 依赖，或在 conftest.py 中全局 mock |
| TD-04 | `TCMLexicon` 接口为占位符，未实现专业中医分词 | 古文分词质量差 | 实现 `src/analysis/tcm_lexicon.py`，集成中医术语词典 |

### 7.2 中优先级债务（质量性）

| ID | 问题 | 建议 |
|----|------|------|
| TD-05 | Qwen 模型提示词散落各处，无统一管理 | 创建 `src/research/prompt_library.py` 集中管理所有 TCM 提示词模板 |
| TD-06 | Neo4j 知识图谱无标准 TCM 本体 Schema | 按第5节类图执行 Cypher 建库脚本（`scripts/init_neo4j_ontology.py`） |
| TD-07 | ChromaDB 使用通用嵌入模型，古文效果差 | 评估 `text2vec-chinese` 或 `m3e-base` 等中文嵌入模型 |
| TD-08 | 无端到端集成测试覆盖 TCM 研究流程 | 添加 `tests/test_tcm_research_flow.py` 和 `tests/test_tcm_literature_methods.py` |

### 7.3 低优先级债务（改善性）

| ID | 问题 | 建议 |
|----|------|------|
| TD-09 | 226 处 f-string 日志调用（非懒加载格式） | 批量替换为 `%s` 格式 |
| TD-10 | 无模块级健康检查 API | 扩展 `/health` 端点返回各模块状态 |
| TD-11 | TCM 文献研究法缺乏 LLM 增强 | 在每个方法的 `analyze()` 中增加可选 LLM 解读参数 |

---

## 8. 分阶段实施计划

```mermaid
gantt
    title 中医古文献研究系统优化路线图
    dateFormat  YYYY-MM
    section Phase 1 基础强化
    解决 TD-01/02 包结构重复    :done, p1a, 2026-01, 2026-02
    解决 TD-03 jieba CI 问题    :done, p1b, 2026-01, 2026-02
    stage2 六种文献研究法实现   :done, p1c, 2026-02, 2026-04
    DocumentPreprocessor 古籍增强 :done, p1d, 2026-03, 2026-04

    section Phase 2 知识图谱完善
    实现 TCMLexicon 专业分词 TD-04   :p2a, 2026-04, 2026-06
    Neo4j TCM 本体建库 TD-06         :p2b, 2026-04, 2026-06
    TCM KnowledgeUpdater 验证        :p2c, 2026-05, 2026-07
    端到端集成测试 TD-08             :p2d, 2026-05, 2026-07

    section Phase 3 AI 增强
    Qwen 提示词库统一管理 TD-05     :p3a, 2026-06, 2026-08
    中文嵌入模型替换 TD-07          :p3b, 2026-06, 2026-09
    TCM 文献方法 LLM 解读集成 TD-11 :p3c, 2026-07, 2026-09

    section Phase 4 自学习闭环
    GraphRAG 集成                    :p4a, 2026-08, 2026-11
    Qwen 领域微调（LoRA）            :p4b, 2026-09, 2026-12
    全自动研究闭环验证               :p4c, 2026-10, 2026-12
```

### 8.1 近期优先行动项（Phase 1 尾声，2026 Q2）

1. **✅ 已完成**：创建 `src/research/tcm_literature_methods.py` — 6种TCM文献研究法
2. **✅ 已完成**：创建 `src/research/tcm_research_flow.py` — 6阶段研究主流程
3. **✅ 已完成**：创建 `src/learning/tcm_knowledge_updater.py` — 知识自更新
4. **✅ 已完成**：增强 `src/analysis/preprocessor.py` — 古籍元数据、异体字规范
5. **✅ 已完成**：更新 `src/research/method_router.py` — 注册6个 `tcm_*` 路由
6. **🔄 进行中**：TD-04 TCMLexicon 实现（当前为占位符）
7. **🔄 进行中**：TD-06 Neo4j TCM 本体建库脚本

### 8.2 Qwen 模型集成建议

| 场景 | 推荐配置 |
|------|---------|
| 古文阅读理解 | temperature=0.3, max_tokens=2048, system_prompt: 中医文献专家角色 |
| 研究报告写作 | temperature=0.5, max_tokens=4096, IMRD 格式约束 |
| 术语训诂解释 | temperature=0.1, max_tokens=512, 严格事实性约束 |
| 研究假设生成 | temperature=0.7, max_tokens=1024, 创新性鼓励 |

---

*文档由 TCM Auto Research System Stage2 架构评审生成*
*基于 T/C IATCM 098-2023 标准 | 版本 2.0.0*
