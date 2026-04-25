# TCM文献半自动科研助手架构分析与演进设计

## 一、当前系统架构概况与实施评估
结合本仓库源码及“中医文献研究法”内容，系统当前定位准确且为“中医文献半自动科研助手”。架构上，具备了模块化单体特征，并由6（后确认为7）阶段主链（ResearchPipeline + PhaseOrchestrator）进行业务流程调度。

### 1. 架构与运行模块评估

| 模块/阶段 | 承担研究法维度的职能 | 当前成熟度与状态 | 优点 | 缺点及技术债 |
|---|---|---|---|---|
| **Collector / Preprocessor**(数据准备) | 文献学层的收集校对、版面数字化，为提取与类编研究提供文本基底。 | ✅ 较高（本地语料 + jieba分词）。 | 解决了基础结构化，提供了可重复执行的数据提取管道。 | 弱对中医特有古籍错略进行字形推断或多版本校验的智能化。 |
| **Philology Service** (文献学分析) | 文献学基础（校勘、辑佚、训诂），这是中医研究不可逾越的前提。 | ✅ 已具备核心契约实现（术语表、辑佚、多义词消歧），Dashboard集成度高。 | 具有配置化的合同契约、明确的置信度评分量化以及严密的审计功能（可写回复核）。 | 朝代规范缺失；依赖规则与字典，未充分利用上下文感知和局部关联做多义消歧；缺乏跨多文本沿袭验证。 |
| **Reasoning / Semantic Graph** (图谱与认知建模) | 类编研究以及知识结构化支撑（实体识别、辨证论治节点及关系的抽取关联）。 | ✅ 知识抽取成熟，可投射到Neo4j；依赖Qwen LLM提取边。 | 双写到 Neo4j 方案已通；基于 NetworkX 及本地图库的建模可以挖掘隐式关联规则。 | 部分边关系抽取准确率依赖静态 Prompt；目前图谱在落库后尚未直接反馈形成知识迭代和持续训练样本。 |
| **Storage Backend** (PG + Neo4j 持久化) | 系统数据的全量长效保存，解决数据孤岛。 | ✅ 已经接线（PG结构数据，Neo4j存图数据）并进行历史回填。 | 从 SQLite 升级，具有了生产级的分析底座；支持事务统筹管理。 | 强依赖双写，虽然开启了事务协调，但若网络/服务故障依然有漂移风险；且目前部分监控逻辑存在异常吞没。 |
| **Self-Learning Loop** (自我学习引擎) | 方法学顶层：积累研究经验、校正研究参数、建立闭环。 | ⚠️ 仅做阶段性日志记录与参数微调统计，未真正改变系统深层认知权重。 | 设立了基于 QualityAssessor 的自适应调整调优（AdaptiveTuner）理论支撑。 | 数据收集大于知识融入。PG与Neo4j积累了上万条数据，但系统并未将其实时提炼出 Pattern 反哺下一次的科研Prompt。 |

---

## 二、真实科研流程运行优点与不足分析

当前系统实现了流程级的跑通（例如 `run_cycle_demo.py` 记录到 PostgreSQL与Neo4j 的双写），但在真实科研环境下，运行存在脱节：

### 优点
1. **统一契约式开发**：各业务链路（包含 Philology 五大合同链）具有明确定义的 JSON 传递契约，利于扩展和维护。
2. **LLM资源高度控制**：设置了完整的 `token_budget` 和 Purpose/Profile 优先级调度，保护本地 `Qwen1.5-7B` 不被爆破显存。
3. **可追溯的领域逻辑**：对提取证据到知识重组、生成结构化汇报具有全程日志追溯审计。

### 不足
1. **实验步骤形同虚设（真实执行脱发）**：文献研究中的“实验与证实”实则是数据挖掘和相关性推论。系统的 Experiment 阶段更像是仅完成“方案规约(Protocol Design)”的编写，这与现实里进行文本聚类、病因病机推演格格不入。
2. **缺乏后置自适应学习**：PostgreSQL与Neo4j已经存载数十份文献数据与几万节点关系，但当前 SelfLearning 并没有抽取Neo4j中的新规则进行“Self-Discover”（推理发现）。
3. **高并发和边界缺陷**：批处理模式及多端调度常出现并发资源竞争，且 Web API / 数据库写入时仍偶发异步锁死，说明上下层解耦并不彻底。

---

## 三、核心优化方案与指令（理由与代价）

### 建议1：重构大模型能力调度与 NLP “Self-Discover” 推理链路
**优化行为**：基于文献学的复杂推理，融合 Google 提出的 Self-Discover 推理模式。将任务区分层级，将基于“发现方剂关联”等高难度操作从静态 Prompt 改为让 Qwen 动态生成多步推理模板，引导从 Neo4j 提取数据去填补模板进行自验证。
* **理由**：单次生成极容易引发事实幻觉；将复杂的中药药性推导演化为先找逻辑框架再提取知识，大幅提升认知精度，切合“中医文献循证研究”理论。
* **代价**：需消耗本地 7B 模型更多 Token，整体处理时延预计增加 2~3 倍，需要重新调整 `llm_purpose_profiles`。

### 建议2：实现 PostgreSQL + Neo4j 数据反推学习环（RAG 与 Graph-RAG 结合）
**优化行为**：在 `SelfLearningEngine` 分离出独立线程，定期拉取 Neo4j 的高频/高置信关系子图（如 某药-对-某病 近10次文献出现），自动生成领域 Few-shot 样本集或修正 `learning_strategies`。并在提取文献时先运行 Graph-RAG 从本地知识库中抓取预知背景增强 LLM 提取。
* **理由**：打通科研沉淀壁垒，把库中死数据盘活成模型微调（SFT）之前的动态语料库。
* **代价**：数据库查询压力增大，需写特定的 Cypher 分析算法；需要建立缓存策略避免读写冲突。

### 建议3：Philology (文献学) 模块的上下文感知增强与深度整合
**优化行为**：扩展 `exegesis_contract.py`，使“多义词消歧”能够调动上下文前100词；实现跨文献版本谱系的沿袭关系交叉比对（比如多篇文献同一方剂的药味变化追踪）。
* **理由**：针对中国中医古籍“同词不同义”（如“伤寒”不同朝代不同意）问题，通过文本窗口加权解决歧义，增强训诂精确性。
* **代价**：上下文计算和匹配导致CPU内存成倍增加；需要重新录入朝代和学派权重映射字典。

### 建议4：系统微服务边界剥离及死代码清理
**优化行为**：完全废弃并移除 `src/research/` 下的所有散落代理（被转移到 `infra` / `collector`），统一合并 `Publish Phase` 与后续冗余输出，废弃脱离实际业务的假 `Experiment`，仅将其退化为“研究提纲拟定”，并重构分析和反射（Reflect）阶段作为知识总结器。
* **理由**：消除技术盲区（Audit已报告30+废弃包）；减少系统内部无谓的参数传递，从而减少 bug，提升可维护性及整体容错能力。
* **代价**：短期会有大量旧分支、测试脚本编译失败，需全仓规模的手动排雷和重构。

---

## 四、系统架构演进图表设计

### 1. 核心文献研究架构类图 (Class Diagram)
体现中医药研究科研助手模块的静态职责：
```mermaid
classDiagram
    class ResearchPipelineOrchestrator {
      +start_research_cycle()
      +dispatch_phase()
    }
    class PhilologyService {
      +disambiguate_polysemy()
      +build_terminology_standard()
      +fragment_reconstruction()
    }
    class DocumentPreprocessor {
      +normalize_layout()
      +jieba_tokenize()
    }
    class SemanticModeler {
      +extract_entities()
      +build_graph()
    }
    class SelfLearningEngine {
      +evaluate_cycle_quality()
      +extract_neo4j_patterns()
      +adjust_strategies()
    }
    class StorageBackendFactory {
      +transaction()
      +pg_persist()
      +neo4j_write()
    }
    
    ResearchPipelineOrchestrator --> PhilologyService
    ResearchPipelineOrchestrator --> DocumentPreprocessor
    ResearchPipelineOrchestrator --> SemanticModeler
    ResearchPipelineOrchestrator --> StorageBackendFactory
    ResearchPipelineOrchestrator --> SelfLearningEngine
    SemanticModeler ..> PhilologyService : Use dictionary
```

### 2. 中医文献科研全流程演进流 (Pipeline Flow)
描述如何通过Graph-RAG和学习闭环改良科研流程：
```mermaid
graph TD
    A[外部古籍 / 文献] -->|收集 & 清洗| B(Document Preprocessor)
    B --> C(Philology Service<br/>考据/校勘/训诂)
    C --> D(Semantic Modeler<br/>实体关系提取)
    D --> E{Qwen1.5-7B<br/>NLP / Graph-RAG增强}
    
    E -->|知识注入/验证| F(Reasoning Engine<br/>推理发现与重组)
    F -->|阶段结果| G[Storage Coordinator]
    G --> H[(PostgreSQL <br/>元数据/资产)]
    G --> I[(Neo4j <br/>语义关系/全景图谱)]
    
    I -.定期挖掘模式.-> J[Self-Learning Engine<br/>动态规则/提效机制]
    J -.修正Prompt配置.-> E
```

### 3. 全局落库与硬件部署部署图 (Deployment Diagram)
针对本地化及高频读写的混合部署策略：
```mermaid
flowchart LR
    subgraph Client
      UI[Web Console / Dashboard]
    end

    subgraph Application Server [Python FastAPI & Pipeline]
      RO[Router Layer API]
      Orch[Research Orchestrator]
      LLMC[LLM Cached Adapter]
      SE[Self-Learning & GraphRAG Task]
      
      UI <--> RO
      RO <--> Orch
      Orch <--> LLMC
      Orch <--> SE
    end

    subgraph LLM Server [GPU - CUDA]
      QW[Qwen1.5-7B-Chat-q8.gguf]
    end

    subgraph Persistence Layer [Dual-Write Storage]
      PG[(PostgreSQL 18.3)]
      N4J[(Neo4j 5.26)]
    end

    LLMC <-->|Llama.cpp| QW
    Orch --> PG
    Orch --> N4J
    SE <--> N4J : Pull high-freq graphs
```

---

## 五、分阶段实施计划

### 阶段 1：废弃剥离与瘦身止血（技术债清理，预计周 1-2）
- **目标**：合并 System A (demo) 与 System B (orchestrator) 的管道分立乱象；清理 `src/research/` 残留约30个冗余包装层；修复Web端并发接口超时及 CloseWait 爆满现象。
- **产出**：一个无断点、入口明确的高可用Python业务后库，主线可直接无缝流转测试用例。
- **具体实施步骤**：
  1. **冗余包装与死代码拔除 (清理 `src/research/`)**
     - *操作*：将 `ctext_corpus_collector.py`、`literature_retriever.py` 等硬编码包装脚本彻底删除或收拢至 `src/collector/`；移除 `src/corpus/`、`src/preprocessor/` 等无实质逻辑仅做转发的残余目录，将调用链直连 `src/analysis/` 与 `src/collector/`。
     - *理由*：消除无意义的代理层，缩短调用栈，降低理解成本与模块间的隐性耦合。
     - *代价*：将波及全局大量 Import 路径，需承担短期内大量模块找不到的编译期错误修复成本。
  2. **主科研架构收敛合并 (System A 迁入 System B)**
     - *操作*：彻底废弃基于过程脚本的 `run_cycle_demo.py` (System A) 及旧版 `cycle_core_demo_handler.py`，提炼其中的有效实体识别与组方推演逻辑，将其编排进 `ResearchPipelineOrchestrator` 主链标准的 7 阶段（重点填充 `Analyze` 与 `Reflect` 阶段）。
     - *理由*：保障所有的 LLM 资源拦截、PostgreSQL/Neo4j 双写、SelfLearning 策略都能在一套生命周期事件网被统一触发，避免出现“平台有底座但业务走后门”的架构跑偏。
     - *代价*：旧有的“一键串行 Demo”短期内无法使用，旧业务流被迫经历打碎重组的阵痛期。
  3. **并发治理与 CloseWait 泄漏修复**
     - *操作*：针对分析 Web 服务（8765 端口）的挂死问题，彻查批量任务 API 里的死锁：1. 将 `requests` 替换为配置了连接池和严格 Timeout 的长连接客户端；2. 在大模型推演层接入基于 `asyncio` 的熔断超时；3. 强化 `StorageBackendFactory` 和 `Neo4jDriver` 的在异常时的 `try...finally` 析构/连接释放。
     - *理由*：中医长文本抽取非常耗时，阻塞会导致 HTTP 连接耗尽并产生大量 CloseWait，必须切断这种雪崩效应才能做后续批处理。
     - *代价*：需引入严格的异步上下文控制，对核心业务 I/O 阻塞处做并发改造。
  4. **E2E测试流转固化**
     - *操作*：针对合并后的 `PhaseOrchestrator`，构建注入最小测试文本集的冒烟测试，断定七阶段走通且 PG 与 Neo4j 预期落库无漂移。
     - *理由*：作为重构“止血”的关键防线，确保瘦身没有误砍主动脉。
     - *代价*：额外投入研发周期的 20% 用于编写、模拟（Mock）及维护集成测试环境。

### 阶段 2：GraphRAG 结合知识融合（双写图分析，预计周 3-5）
- **目标**：强化 `SemanticModeler`，引入基于 Neo4j 提取全量古籍脉络数据做底座，结合本地 Qwen1.5 在生成输出前通过向量相似与节点相连，执行 Graph-RAG 召回补充，解决局部提取时的偏颇偏差。
- **产出**：通过查询验证，能自动追溯“同类药方在不同文献分布”的完整链条分析。

### 阶段 3：文献学认知强化（Philology 上下文加权，预计周 6-7）
- **目标**：改造 `philology_service.py` 内部 `disambiguate_polysemy`，取消单维度判断；结合最新 NLP 自验证理论 (Self-Discover/Self-Refine)，加入朝代与前后置文本的 LLM 推理判定。
- **产出**：术语释义、病性病机识别准确率（尤其对于上古文献异体字及古义）显著上升。

### 阶段 4：常态自学习环道上线（自适调整与挖掘，预计周 8-9）
- **目标**：实现对存储数据的“沉淀挖掘”；建立定时守护脚本（或系统空闲时挂起后台队列），拉取 Neo4j 的增量节点图进行图聚合提鲜，作为科研循环下一次分析的历史参考底座。
- **产出**：系统应用越久，由于其动态积累样本调配 Prompt，推理精度能自动超越基线阈值，表现为一个自我滋养的中医脑。