# 中医古籍研究系统 - 分析存储架构方案
**日期**：2026-03-28  
**版本**：1.0

---

## 一、系统现状分析

### 1.1 数据流链条（当前状态）

```
文本输入 → 文档预处理 → 实体抽取 → 语义建模 → 推理分析 → 输出生成 → JSON文件
   ↓          ↓           ↓          ↓           ↓          ↓
 raw_text   preproc    entities  sem_graph   reason    output.json
          text        + stats   + analysis   + temp     (output/*)
```

### 1.2 当前存储方式
- **存储位置**：`./output/` 目录
- **存储格式**：JSON文件
- **主要依赖**：无数据库，全内存处理，最后序列化

### 1.3 数据流向分析

#### 核心模块及其数据流出
| 模块 | 输入 | 输出 | 数据特征 |
|---|----|---|----|
| DocumentPreprocessor | 原始文本 | 清理文本、元数据 | 文本序列、清理规则统计 |
| AdvancedEntityExtractor | 清理文本 | entities[] + statistics | 结构化实体集合，置信度评分 |
| SemanticGraphBuilder | entities[] | 知识图（节点+边） | NetworkX MultiDiGraph，含君臣佐使关系 |
| ReasoningEngine | 图数据 + entities | 推理结果、模式识别 | 关系链、推理链路、时间维度分析 |
| OutputGenerator | 全部中间结果 | 最终JSON输出 | 标准化学术报告格式 |

---

## 二、数据特征分类

### 2.1 需要持久化的数据类型

#### A. **结构化表格数据**（适合 PostgreSQL）

**1. 核心实体表**
```
entities
  ├─ id (UUID PK)
  ├─ name (VARCHAR)
  ├─ type (ENUM: formula|herb|syndrome|efficacy)
  ├─ confidence (FLOAT 0-1)
  ├─ position (INT)
  ├─ length (INT)
  ├─ source_document_id (FK → documents)
  ├─ created_at (TIMESTAMP)
  └─ updated_at (TIMESTAMP)
```

**2. 文档表**
```
documents
  ├─ id (UUID PK)
  ├─ source_file (VARCHAR)
  ├─ processing_timestamp (TIMESTAMP)
  ├─ objective (VARCHAR)
  ├─ raw_text_size (INT)
  ├─ entities_extracted_count (INT)
  ├─ process_status (ENUM: pending|processing|completed|failed)
  └─ quality_score (FLOAT 0-1)
```

**3. 关系定义表**
```
relationship_types
  ├─ id (UUID PK)
  ├─ relationship_name (VARCHAR UNIQUE)
  ├─ relationship_type (VARCHAR)
  ├─ description (TEXT)
  └─ confidence_baseline (FLOAT)
```

**4. 实体关系表**（关联表，而非存在Neo4j中）
```
entity_relationships
  ├─ id (UUID PK)
  ├─ source_entity_id (FK → entities)
  ├─ target_entity_id (FK → entities)
  ├─ relationship_type_id (FK → relationship_types)
  ├─ confidence (FLOAT)
  ├─ created_by_module (VARCHAR)
  └─ created_at (TIMESTAMP)
```

**5. 统计数据表**
```
processing_statistics
  ├─ id (UUID PK)
  ├─ document_id (FK → documents)
  ├─ formulas_count (INT)
  ├─ herbs_count (INT)
  ├─ syndromes_count (INT)
  ├─ efficacies_count (INT)
  ├─ relationships_count (INT)
  └─ graph_density (FLOAT)
```

**6. 质量指标表**
```
quality_metrics
  ├─ id (UUID PK)
  ├─ document_id (FK → documents)
  ├─ confidence_score (FLOAT)
  ├─ completeness (FLOAT)
  ├─ entity_precision (FLOAT)
  ├─ relationship_precision (FLOAT)
  ├─ evaluation_timestamp (TIMESTAMP)
  └─ evaluator (VARCHAR)
```

**7. 处理日志表**
```
processing_logs
  ├─ id (UUID PK)
  ├─ document_id (FK → documents)
  ├─ module_name (VARCHAR)
  ├─ status (ENUM: start|success|failure)
  ├─ message (TEXT)
  ├─ error_details (TEXT)
  ├─ execution_time_ms (INT)
  └─ timestamp (TIMESTAMP)
```

---

#### B. **图数据**（适合 Neo4j）

**节点类型**：
- **Formula（方剂）**：name, alias, origin, properties...
- **Herb（药物）**：name, alias, nature, flavor, meridian...
- **Syndrome（症候）**：name, description, classification...
- **Efficacy（功效）**：name, category, description...

**边类型**：
- **SOVEREIGN（君）**：Formula → Herb（principle herb）
- **MINISTER（臣）**：Formula → Herb（assistant herb）
- **ASSISTANT（佐）**：Formula → Herb（supporting herb）
- **ENVOY（使）**：Formula → Herb（coordinating herb）
- **TREATS（治疗）**：Formula/Herb → Syndrome
- **HAS_EFFICACY（具有功效）**：Herb/Formula → Efficacy
- **SIMILAR_TO（类似）**：Formula → Formula
- **CONTAINS（包含）**：Formula → Herb

**边属性**：
```json
{
  "relationship_type": "SOVEREIGN",
  "confidence": 0.95,
  "created_at": "2026-03-28T10:30:00Z",
  "source_module": "semantic_graph_builder",
  "evidence_count": 3
}
```

---

#### C. **分析研究数据**（存储策略：JSON字段 in PostgreSQL + Neo4j 属性）

**存储在 PostgreSQL JSON字段**：
```
research_analyses
  ├─ id (UUID PK)
  ├─ document_id (FK → documents)
  ├─ research_perspectives (JSONB)
  ├─ formula_comparisons (JSONB)
  ├─ herb_properties_analysis (JSONB)
  ├─ pharmacology_integration (JSONB)
  ├─ network_pharmacology (JSONB)
  ├─ supramolecular_physicochemistry (JSONB)
  ├─ knowledge_archaeology (JSONB)
  ├─ complexity_dynamics (JSONB)
  ├─ research_scoring_panel (JSONB)
  ├─ summary_analysis (JSONB)
  └─ created_at (TIMESTAMP)
```

**为什么用JSONB**：
- 研究数据结构复杂且动态
- 支持灵活的查询（PostgreSQL JSONB强大的查询能力）
- 易于扩展新的分析维度

---

### 2.2 数据访问模式

| 访问场景 | 存储系统 | 查询方式 |
|---------|--------|--------|
| 查找特定方剂的组成 | Neo4j | `MATCH (f:Formula {name})-[r:SOVEREIGN\|MINISTER\|...]->(h:Herb) RETURN h` |
| 查找所有治疗某证候的方剂 | Neo4j | `MATCH (f:Formula)-[:TREATS]->(s:Syndrome {name}) RETURN f` |
| 查询实体的处理历史 | PostgreSQL | `SELECT * FROM entity_relationships WHERE source_entity_id = ? ORDER BY created_at DESC` |
| 获取文档的质量报告 | PostgreSQL | `SELECT * FROM quality_metrics WHERE document_id = ?` |
| 统计处理统计数据 | PostgreSQL | `SELECT AVG(confidence), COUNT(*) FROM entity_relationships GROUP BY relationship_type_id` |
| 跨图和表的复杂分析 | 两者结合 | 先从Neo4j获取图结构，再从PostgreSQL验证和统计 |

---

## 三、存储架构设计

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│         中医古籍研究系统 - 统一存储架构                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   ┌───────────────────┐      ┌──────────────────┐     │
│   │   应用层 (Python) │      │  前端/查询层     │     │
│   └─────────┬─────────┘      └────────┬─────────┘     │
│             │                         │                │
│   ┌─────────▼──────────────────────────▼─────┐         │
│   │      统一 ORM 及存储驱动层                │         │
│   │  (storage_driver.py / db_models.py)     │         │
│   └──────────────┬────────────────┬──────────┘         │
│                  │                │                   │
│        ┌─────────▼─┐    ┌─────────▼───────┐           │
│        │PostgreSQL │    │    Neo4j 5.26   │           │
│        │  数据库   │    │    图数据库     │           │
│        │           │    │                 │           │
│        │ 结构化    │    │  图结构数据     │           │
│        │ 关系数据  │    │  实时图查询     │           │
│        │ 分析数据  │    │  路径发现       │           │
│        └─────────┬─┘    └─────────┬───────┘           │
│                  │                │                   │
│        ┌─────────▼────────────────▼─────┐             │
│        │     持久化文件存储 (optional)   │             │
│        │   - 导出JSON/CSV/XML           │             │
│        │   - 备份快照                    │             │
│        └───────────────────────────────┘             │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 3.2 存储系统选择理由

| 系统 | 为什么选择 | 存储内容 | 访问特性 |
|-----|---------|--------|--------|
| **PostgreSQL** | ✅ ACID事务、JSON支持、强大查询能力、生态完善 | 结构化元数据、统计分析、审计日志、JSON研究数据 | 行/列查询、索引优化、复杂JOIN |
| **Neo4j** | ✅ 原生图数据库、关系查询高效、可视化、推荐算法 | 知识图（节点+边）、君臣佐使关系、相似性 | 路径查询、关系遍历、中心性分析 |

---

## 四、数据流改造方案

### 4.1 新数据流

```
入口数据
   ↓
┌─────────────────────┐
│  DocumentPreproc    │
└──────────┬──────────┘
           ↓ [A] 存储原文本元信息 → PostgreSQL (documents)
┌─────────────────────┐
│ entityExtractor     │
└──────────┬──────────┘
           ↓ [B] 存储实体 → PostgreSQL (entities) + Neo4j (Nodes)
┌─────────────────────┐
│ SemanticGraphBuilder│
└──────────┬──────────┘
           ↓ [C] 存储关系 → PostgreSQL (entity_relationships) + Neo4j (Edges)
           ↓ [D] 存储图统计 → PostgreSQL (processing_statistics)
┌─────────────────────┐
│  ReasoningEngine    │
└──────────┬──────────┘
           ↓ [E] 存储推理结果 → PostgreSQL (research_analyses)
┌─────────────────────┐
│ OutputGenerator     │
└──────────┬──────────┘
           ↓ [F] 最终输出 → JSON + 存档参考
```

### 4.2 存储时机与优先级

| 优先级 | 数据 | 存储时机 | 目标库 | 是否必须 |
|------|-----|--------|------|--------|
| P0 | entities | EntityExtractor完成后 | PostgreSQL + Neo4j | ✅ 必须 |
| P0 | relationships | SemanticGraphBuilder完成后 | PostgreSQL + Neo4j | ✅ 必须 |
| P1 | documents元信息 | DocumentPreprocessor完成后 | PostgreSQL | ✅ 必须 |
| P1 | statistics | SemanticGraphBuilder完成后 | PostgreSQL | ✅ 必须 |
| P2 | research_analyses | ReasoningEngine完成后 | PostgreSQL (JSONB) | ⚠️ 可选 |
| P3 | 最终JSON | OutputGenerator完成后 | 文件系统 | ⚠️ 可选 |

---

## 五、数据库连接配置

### 5.1 PostgreSQL 配置

```yaml
# config.yml 补充
databases:
  postgresql:
    enabled: true
    driver: psycopg2
    host: localhost
    port: 5432
    database: tcm_autoresearch
    user: tcm_user
    password: ${DB_PASSWORD}  # 环境变量
    pool_size: 10
    max_overflow: 20
    echo: false
    
  neo4j:
    enabled: true
    uri: neo4j://localhost:7687  # 默认端口
    auth: (neo4j_user, ${NEO4J_PASSWORD})
    database: neo4j
    trust: TRUST_SYSTEM_CA_SIGNED_CERTIFICATES
```

### 5.2 表生成脚本

参见 `src/storage/database_schema.sql`

### 5.3 ORM 模型

参见 `src/storage/db_models.py`

---

## 六、实现路线图

### Phase 1：基础设施（第1周）
- [ ] 创建PostgreSQL数据库和Schema
- [ ] 创建Neo4j数据库和角色
- [ ] 实现SQLAlchemy ORM模型 (`db_models.py`)
- [ ] 实现数据库连接管理器 (`db_manager.py`)

### Phase 2：核心集成（第2周）
- [ ] 修改 EntityExtractor：存储实体到PostgreSQL + Neo4j
- [ ] 修改 SemanticGraphBuilder：存储关系和图统计
- [ ] 修改 OutputGenerator：添加数据库写入逻辑
- [ ] 添加事务管理和错误处理

### Phase 3：查询优化（第3周）
- [ ] 创建数据查询服务层 (`query_service.py`)
- [ ] 添加索引和查询优化
- [ ] 创建备份和恢复脚本

### Phase 4：可观测性（第4周）
- [ ] 添加处理日志记录
- [ ] 创建数据质量监控
- [ ] 创建数据导出工具

---

## 七、关键配置文件清单

| 文件 | 位置 | 功能 |
|---|----|------|
| database_schema.sql | `src/storage/` | PostgreSQL初始化脚本 |
| db_models.py | `src/storage/` | SQLAlchemy ORM模型定义 |
| db_manager.py | `src/storage/` | 数据库连接管理 |
| neo4j_driver.py | `src/storage/` | Neo4j连接和操作 |
| storage_driver.py | `src/storage/` | 统一存储驱动接口 |
| query_service.py | `src/storage/` | 查询服务层 |

---

## 八、风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 数据库连接失败 | 系统无法启动 | 实现重试机制、降级策略（Fallback to JSON） |
| 性能瓶颈 | 处理速度下降 | 异步批量写入、连接池优化、查询索引 |
| 数据一致性 | 不同库间数据不同步 | 事务管理、同步写入、数据验证脚本 |
| 存储容量溢出 | 磁盘满 | 定期备份、数据清理策略、分区表 |

---

## 九、术语对照表

| 中文术语 | 英文 | 存储位置 | 备注 |
|--------|-----|--------|------|
| 方剂 | Formula | Neo4j Node | 配方、汤液 |
| 中药 | Herb | Neo4j Node | 药物、单体 |
| 症候 | Syndrome | Neo4j Node | 病证、证候 |
| 功效 | Efficacy | Neo4j Node | 主治、作用 |
| 君臣佐使 | SOVEREIGN/MINISTER/ASSISTANT/ENVOY | Neo4j Edge | 方剂组成关系 |
| 治疗 | TREATS | Neo4j Edge | 有效性关系 |
| 置信度 | Confidence | 两库 | 0-1评分 |

---

## 十、监控指标

```python
# 定期监控指标
metrics = {
    "entity_count": "SELECT COUNT(*) FROM entities",
    "relationship_count": "SELECT COUNT(*) FROM entity_relationships",
    "graph_density": "SELECT * FROM processing_statistics ORDER BY created_at DESC LIMIT 1",
    "sync_lag": "复核PostgreSQL和Neo4j数据一致性",
    "query_response_time": "监控关键查询的平均响应时间"
}
```

---

**后续文档**：
- `STORAGE_IMPLEMENTATION.md`：详细实现指南
- `STORAGE_QUERIES.md`：常用查询集合
- `STORAGE_MIGRATION.md`：数据迁移脚本

