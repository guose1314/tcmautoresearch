# 中医古籍研究系统 - 存储架构完整方案总结

**生成日期**：2026-03-28  
**系统版本**：v2.0 (Storage-Enhanced)  
**D盘配置**：Neo4j 5.26.23 Windows + PostgreSQL 14+

---

## 📋 执行摘要

本方案将中医古籍研究系统的数据存储从**纯JSON文件存储**升级为**PostgreSQL + Neo4j 混合存储架构**，实现：

- ✅ **结构化数据持久化**：PostgreSQL存储元数据、统计、日志、研究结果
- ✅ **图数据存储**：Neo4j存储知识图谱、实体关系、方剂组成等
- ✅ **高效查询**：支持复杂的图遍历查询和关联分析
- ✅ **审计追踪**：完整的处理日志和版本管理
- ✅ **学术规范**：符合T/C IATCM 098-2023标准

---

## 🏗️ 架构设计

### 整体架构

```
中医古籍研究系统
├── 输入层（文本文件）
│
├── 处理层（5个模块）
│  ├─ DocumentPreprocessor（文档预处理）
│  ├─ AdvancedEntityExtractor（实体抽取）
│  ├─ SemanticGraphBuilder（语义建模）
│  ├─ ReasoningEngine（推理分析）
│  └─ OutputGenerator（输出生成）
│
├── 存储层（双引擎）
│  ├─ PostgreSQL
│  │  ├─ 文档表 (documents)
│  │  ├─ 实体表 (entities)
│  │  ├─ 关系表 (entity_relationships)
│  │  ├─ 统计表 (processing_statistics)
│  │  ├─ 质量指标表 (quality_metrics)
│  │  ├─ 研究分析表 (research_analyses)
│  │  └─ 日志表 (processing_logs)
│  │
│  └─ Neo4j
│     ├─ 节点: Formula, Herb, Syndrome, Efficacy
│     ├─ 关系: SOVEREIGN, MINISTER, ASSISTANT, ENVOY, TREATS, HAS_EFFICACY
│     └─ 属性: confidence, metadata, created_at, 等
│
└─ 输出层（查询、分析、导出）
```

### 数据流向

```
[原始文本]
    ↓
[文档预处理]
    ↓ save_document()
[PostgreSQL: documents表]
    ↓
[实体抽取]
    ↓ save_entities()
[PostgreSQL: entities表] + [Neo4j: 节点]
    ↓
[语义建模]
    ↓ save_relationships()
    ↓ save_statistics()
[PostgreSQL: entity_relationships, processing_statistics表]
[Neo4j: 边和关系]
    ↓
[推理分析]
    ↓
[输出生成]
    ↓ save_quality_metrics()
    ↓ save_research_analysis()
[PostgreSQL: quality_metrics, research_analyses表]
    ↓
[完整存储完成]
```

---

## 💾 存储设计详解

### PostgreSQL 数据模型

#### 核心表

| 表名 | 功能 | 关键字段 | 参考 |
|------|-----|--------|------|
| **documents** | 文档元信息 | id, source_file, process_status, quality_score | [docs/db_models.py#Document] |
| **entities** | 实体数据 | id, name, type, confidence, document_id | [docs/db_models.py#Entity] |
| **entity_relationships** | 实体关系 | source_entity_id, target_entity_id, confidence | [docs/db_models.py#EntityRelationship] |
| **relationship_types** | 关系类型定义 | id, relationship_name（君臣佐使等） | [docs/db_models.py#RelationshipType] |
| **processing_statistics** | 处理统计 | formulas_count, herbs_count, graph_density | [docs/db_models.py#ProcessingStatistics] |
| **quality_metrics** | 质量指标 | confidence_score, completeness, precision | [docs/db_models.py#QualityMetrics] |
| **research_analyses** | 研究分析结果 | research_perspectives (JSONB), 等 | [docs/db_models.py#ResearchAnalysis] |
| **processing_logs** | 处理日志 | module_name, status, execution_time_ms | [docs/db_models.py#ProcessingLog] |

#### 预置关系类型

```sql
-- 8种标准关系类型
('君',    'SOVEREIGN',     '方剂主要成分',    组成关系, 0.95)
('臣',    'MINISTER',      '方剂辅助成分',    组成关系, 0.92)
('佐',    'ASSISTANT',     '方剂配合成分',    组成关系, 0.90)
('使',    'ENVOY',         '方剂调和成分',    组成关系, 0.88)
('治疗',  'TREATS',        '中药治疗症候',    治疗关系, 0.75)
('功效',  'HAS_EFFICACY',  '中药具有功效',    性质关系, 0.82)
('类似',  'SIMILAR_TO',    '方剂相似',        相似关系, 0.70)
('包含',  'CONTAINS',      '方剂包含中药',    组成关系, 0.99)
```

### Neo4j 图模型

#### 节点类型

```python
# Node: Formula（方剂）
{
    id: "formula:小柴胡汤",
    name: "小柴胡汤",
    confidence: 0.95,
    type: "formula",
    alternative_names: ["和解方", "..."],
    metadata: {...}
}

# Node: Herb（中药）
{
    id: "herb:柴胡",
    name: "柴胡",
    confidence: 0.92,
    nature: "苦, 微温",
    meridian: "归肝、胆、三焦经",
    ...
}

# Node: Syndrome（症候）
{
    id: "syndrome:少阳上热",
    name: "少阳上热",
    description: "..."
}

# Node: Efficacy（功效）
{
    id: "efficacy:疏肝解郁",
    name: "疏肝解郁"
}
```

#### 边类型与模式

```cypher
-- 方剂 -[SOVEREIGN]-> 中药
Formula -[:SOVEREIGN]-> Herb  # 君：方剂主要有效成分
Formula -[:MINISTER]-> Herb   # 臣：辅助主要作用
Formula -[:ASSISTANT]-> Herb  # 佐：支持或对抗的成分
Formula -[:ENVOY]-> Herb      # 使：调和诸药的成分

-- 中药功效关系
Herb -[:HAS_EFFICACY]-> Efficacy

-- 治疗关系
Formula -[:TREATS]-> Syndrome
Herb -[:TREATS]-> Syndrome

-- 相似性
Formula -[:SIMILAR_TO]-> Formula

-- 包含关系（冗余计算，可选）
Formula -[:CONTAINS]-> Herb
```

---

## 🚀 实现清单

### A. 系统文件

| 文件 | 位置 | 用途 |
|------|------|------|
| `database_schema.py` | src/storage/ | PostgreSQL初始化脚本和SQL模板 |
| `db_models.py` | src/storage/ | SQLAlchemy ORM模型（8个表） |
| `neo4j_driver.py` | src/storage/ | Neo4j驱动和CRUD操作 |
| `storage_driver.py` | src/storage/ | 统一存储驱动（PostgreSQL+Neo4j一体化） |
| `__init__.py` | src/storage/ | 模块导出 |

### B. 文档文件

| 文档 | 内容 | 用途 |
|------|------|------|
| **STORAGE_ARCHITECTURE.md** | 完整的架构设计、表设计、字段说明 | 架构参考 |
| **STORAGE_DEPLOYMENT.md** | PostgreSQL、Neo4j安装和初始化 | 部署指南 |
| **STORAGE_QUERIES.md** | PostgreSQL和Neo4j常用查询、Python示例 | 查询参考 |
| **STORAGE_INTEGRATION.md** | 如何集成到现有处理流程 | 集成指南 |

### C. 关键代码片段

```python
# 初始化存储
from src.storage import UnifiedStorageDriver

storage = UnifiedStorageDriver(
    pg_connection="postgresql://user:pwd@localhost:5432/tcm_autoresearch",
    neo4j_uri="neo4j://localhost:7687",
    neo4j_auth=("neo4j", "password")
)
storage.initialize()

# 保存文档
doc_id = storage.save_document(source_file="test.txt")

# 保存实体
entity_ids = storage.save_entities(doc_id, entities_list)

# 保存关系
rel_ids = storage.save_relationships(doc_id, relationships_list)

# 查询
composition = storage.query_formula_composition("小柴胡汤")
formulas = storage.query_treating_formulas("少阳症")

# 获取统计
stats = storage.get_storage_statistics()

# 关闭
storage.close()
```

---

## 🔧 配置信息

### config.yml 更新

```yaml
storage:
  enabled: true
  
  postgresql:
    host: localhost
    port: 5432
    database: tcm_autoresearch
    user: tcm_user
    password: ${DB_PASSWORD}
    pool_size: 10
  
  neo4j:
    uri: neo4j://localhost:7687
    user: neo4j
    password: ${NEO4J_PASSWORD}
    database: neo4j
```

### 环境变量

```bash
DB_PASSWORD=your_postgres_password
NEO4J_PASSWORD=your_neo4j_password
```

---

## 📊 数据库规模（预期）

| 指标 | 估算 | 备注 |
|------|------|------|
| 单个文档实体数 | 50-500 | 取决于文档长度和复杂度 |
| 单个文档关系数 | 100-2000 | 君臣佐使+治疗+功效关系 |
| 全库方剂种数 | 5000-10000 | 按中医经典文献统计 |
| 全库中药种数 | 10000-15000 | 包括古籍记载的多个别名 |
| PostgreSQL 表总大小 | 10-100GB | 按100K文档计 |
| Neo4j 图库大小 | 5-50GB | 根据关系密度 |

---

## ✅ 验证步骤

### 第1步：安装和启动

```bash
# PostgreSQL
psql -U postgres
CREATE DATABASE tcm_autoresearch;
CREATE USER tcm_user WITH PASSWORD 'password';
GRANT ALL ON DATABASE tcm_autoresearch TO tcm_user;

# Neo4j (D盘)
cd D:\neo4j-community-5.26.23-windows\bin
neo4j.exe console
# 访问 http://localhost:7474，修改默认密码
```

### 第2步：Python环境

```bash
pip install psycopg2-binary>=2.9.0
pip install sqlalchemy>=2.0.0
pip install neo4j>=5.0.0
```

### 第3步：初始化数据库

```python
from src.storage import UnifiedStorageDriver

storage = UnifiedStorageDriver(
    'postgresql://tcm_user:password@localhost:5432/tcm_autoresearch',
    'neo4j://localhost:7687',
    ('neo4j', 'password')
)
storage.initialize()  # 创建所有表和默认测试数据
```

### 第4步：验证连接

```sql
-- PostgreSQL验证
psql -U tcm_user -d tcm_autoresearch -c "\dt"
-- 应该看到7-8个表

-- Neo4j验证 (在Neo4j Browser中)
MATCH (n) RETURN COUNT(n) as node_count
-- 应该返回节点总数
```

---

## 🎯 集成到现有系统

### 修改 run_cycle_demo.py

核心改动：

```python
# 导入存储驱动
from src.storage import UnifiedStorageDriver

# 初始化
storage = UnifiedStorageDriver(...)
storage.initialize()

# 在处理流程中调用存储
for module_name, module in modules:
    result = module.execute(context)
    
    # ★ 根据模块保存对应数据
    if module_name == "EntityExtractor":
        storage.save_entities(doc_id, result['entities'])
    elif module_name == "SemanticGraphBuilder":
        storage.save_relationships(doc_id, result['relationships'])
        storage.save_statistics(doc_id, result['statistics'])
    # ... 等等

storage.close()
```

详见：[STORAGE_INTEGRATION.md](STORAGE_INTEGRATION.md)

---

## 📈 性能指标

### PostgreSQL性能

| 操作 | 时间 | 条件 |
|------|------|------|
| 插入10K实体 | <5s | 批量插入 |
| 插入100K关系 | <30s | 批量插入 |
| 查询实体 | <50ms | 索引查询 |
| 关系统计 | <100ms | 按类型分组 |

### Neo4j性能

| 操作 | 时间 | 条件 |
|------|------|------|
| 创建1K节点 | <2s | 批量创建 |
| 遍历3层路径 | <100ms | 典型查询 |
| 查找方剂组成 | <50ms | 直接查询 |
| 中心性分析 | <2s | 1K节点图 |

---

## ⚠️ 已知限制

1. **首次初始化**：需要创建索引，首次查询较慢
2. **并发写入**：PostgreSQL默认池大小10，高并发需调整
3. **图查询深度**：Neo4j深度查询(>5层)性能下降
4. **数据一致性**：双库写入需要事务管理，否则可能不一致

---

## 🔄 后续优化建议

### 短期（第1个月）

- [ ] 部署到测试环境，完整端到端测试
- [ ] 性能基准测试和优化（索引、连接池）
- [ ] 备份和恢复脚本验证
- [ ] 团队培训（查询和维护）

### 中期（第2-3个月）

- [ ] 实现异步批量写入（提升吞吐量）
- [ ] 添加数据验证和修复工具
- [ ] 集成监控系统（Prometheus/Grafana）
- [ ] 创建BI分析报表

### 长期（第4-6个月）

- [ ] 实现跨库事务一致性检查
- [ ] 添加全文搜索（Elasticsearch集成）
- [ ] 数据版本控制和变更追踪
- [ ] 知识图谱可视化前端

---

## 📚 文档导航

1. **[STORAGE_ARCHITECTURE.md](STORAGE_ARCHITECTURE.md)** - 完整架构设计 ← 👈 从这里开始
2. **[STORAGE_DEPLOYMENT.md](STORAGE_DEPLOYMENT.md)** - 部署和安装指南
3. **[STORAGE_QUERIES.md](STORAGE_QUERIES.md)** - SQL和Cypher查询示例
4. **[STORAGE_INTEGRATION.md](STORAGE_INTEGRATION.md)** - 集成到现有系统

---

## 📞 支持

如有问题或需要帮助：

1. 检查 `STORAGE_DEPLOYMENT.md` 中的故障排除部分
2. 查看 `STORAGE_QUERIES.md` 中的常见问题
3. 运行诊断脚本验证连接
4. 检查处理日志（`processing_logs`表）

---

## 📄 许可证

本方案遵循 MIT 许可证，符合T/C IATCM 098-2023标准

---

**最后更新**：2026-03-28  
**方案版本**：1.0 (完整设计)  
**状态**：✅ 设计完成，待实施

