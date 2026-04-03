# 📦 项目存储架构 - 完整交付清单

## 📋 交付物清单

### 1. 核心代码模块 (src/storage/)

#### 🔧 实现文件

```
src/storage/
├── __init__.py                 # 模块导出和API
├── database_schema.py          # PostgreSQL Schema定义（SQL初始化脚本）
├── db_models.py               # SQLAlchemy ORM模型（8张表具体实现）
├── neo4j_driver.py            # Neo4j驱动和图操作
└── storage_driver.py          # 统一存储驱动（PostgreSQL + Neo4j一体化）
```

**文件说明**：

| 文件 | 代码行数 | 关键类/函数 | 功能 |
|------|--------|-----------|------|
| db_models.py | ~450 | Document, Entity, EntityRelationship等8个ORM类 | 定义所有数据表结构 |
| neo4j_driver.py | ~350 | Neo4jDriver, Neo4jNode, Neo4jEdge | 图数据库操作接口 |
| storage_driver.py | ~500 | UnifiedStorageDriver | 统一接口，同时管理PostgreSQL和Neo4j |
| database_schema.py | ~200 | SQL初始化脚本，视图定义 | PostgreSQL初始化 |

---

### 2. 配置和部署文档

#### 📖 参考文档（4份）

```
项目根目录/
├── STORAGE_ARCHITECTURE.md      ← 【从这里开始】完整架构设计（800行）
├── STORAGE_DEPLOYMENT.md        ← 部署指南（含Windows安装步骤）（400行）
├── STORAGE_QUERIES.md           ← SQL/Cypher查询示例和Python使用例（600行）
├── STORAGE_INTEGRATION.md       ← 集成到现有系统（400行）
└── STORAGE_PLAN_SUMMARY.md      ← 本方案总结（250行）
```

**文档导航图**：

```
STORAGE_PLAN_SUMMARY.md (总览)
    ↓
    ├→ STORAGE_ARCHITECTURE.md (详细设计)
    │   ├─ 数据模型
    │   ├─ 表结构
    │   └─ 存储策略
    │
    ├→ STORAGE_DEPLOYMENT.md (部署)
    │   ├─ PostgreSQL安装
    │   ├─ Neo4j安装
    │   └─ 故障排除
    │
    ├→ STORAGE_QUERIES.md (查询)
    │   ├─ SQL查询集合
    │   ├─ Cypher查询集合
    │   └─ Python示例
    │
    └→ STORAGE_INTEGRATION.md (集成)
        ├─ 修改run_cycle_demo.py
        ├─ 配置config.yml
        └─ 环境变量设置
```

---

## 🗂️ 完整项目结构

```
tcmautoresearch/
│
├── 📄 配置文件
│   ├── config.yml                        # 【需更新】添加storage配置
│   ├── requirements.txt                  # 【需更新】添加依赖
│   └── .env                              # 【新增】环境变量文件
│
├── 📚 文档（新增）
│   ├── STORAGE_PLAN_SUMMARY.md          # ⭐ 总体方案(260行)
│   ├── STORAGE_ARCHITECTURE.md          # ⭐ 详细架构(800行)
│   ├── STORAGE_DEPLOYMENT.md            # ⭐ 部署指南(400行)
│   ├── STORAGE_QUERIES.md               # ⭐ 查询参考(600行)
│   └── STORAGE_INTEGRATION.md           # ⭐ 集成指南(400行)
│
├── 📦 源代码
│   ├── src/
│   │   ├── storage/                     # 🆕【新模块】存储驱动
│   │   │   ├── __init__.py              # 模块导出(50行)
│   │   │   ├── database_schema.py       # Schema定义(200行)
│   │   │   ├── db_models.py             # ORM模型(450行)
│   │   │   ├── neo4j_driver.py          # Neo4j驱动(350行)
│   │   │   └── storage_driver.py        # 统一驱动(500行)
│   │   │
│   │   └── [其他现有模块...]
│   │
│   ├── tests/                           # 【可选】存储单元测试
│   └── examples/                        # 【可选】使用示例
│
└── 📋 根目录其他文件
    ├── README.md                        # 【需更新】添加存储说明
    └── run_cycle_demo.py                # 【需修改】集成存储调用
```

---

## 🎯 核心功能

### 1. 数据入库流程

```python
# 完整示例
from src.storage import UnifiedStorageDriver

# 初始化
storage = UnifiedStorageDriver(
    pg_connection="postgresql://tcm_user:pwd@localhost:5432/tcm_autoresearch",
    neo4j_uri="neo4j://localhost:7687",
    neo4j_auth=("neo4j", "password")
)
storage.initialize()  # 创建所有表和关系类型

# 步骤1：保存文档
doc_id = storage.save_document("source.txt", "分析方剂组成", raw_text_size=5000)

# 步骤2：保存实体
entities = [
    {"name": "小柴胡汤", "type": "formula", "confidence": 0.95, ...},
    {"name": "柴胡", "type": "herb", "confidence": 0.92, ...},
    ...
]
entity_ids = storage.save_entities(doc_id, entities)

# 步骤3：保存关系
relationships = [
    {
        "source_entity_id": entity_ids[0],  # 小柴胡汤
        "target_entity_id": entity_ids[1],  # 柴胡
        "relationship_type": "SOVEREIGN",   # 君
        "confidence": 0.95
    },
    ...
]
rel_ids = storage.save_relationships(doc_id, relationships)

# 步骤4：保存统计信息
stats = {
    "formulas_count": 10,
    "herbs_count": 50,
    "graph_density": 0.28,
    ...
}
storage.save_statistics(doc_id, stats)

# 步骤5：保存质量指标
quality = {
    "confidence_score": 0.88,
    "completeness": 0.92,
    ...
}
storage.save_quality_metrics(doc_id, quality)

# 步骤6：保存研究分析
analysis = {
    "research_perspectives": {...},
    "formula_comparisons": {...},
    ...
}
storage.save_research_analysis(doc_id, analysis)

storage.close()
```

### 2. 数据查询示例

```python
# PostgreSQL 查询
entities = storage.get_entities(doc_id)
relationships = storage.get_relationships(doc_id)

# Neo4j 图查询
composition = storage.query_formula_composition("小柴胡汤")
# 返回: {sovereign: [...], minister: [...], assistant: [...], envoy: [...]}

treating_formulas = storage.query_treating_formulas("少阳症")
# 返回: [{"name": "小柴胡汤", "confidence": 0.85}, ...]

# 统计信息
stats = storage.get_storage_statistics()
# 返回: {postgresql: {...}, neo4j: {...}}
```

---

## 📊 数据库设计摘要

### PostgreSQL 表结构一览

```sql
-- 1. 源文件追踪
documents
  id | source_file | process_status | quality_score | created_at
  
-- 2. 实体数据
entities
  id | document_id | name | type | confidence | metadata
  
-- 3. 关系定义
relationship_types
  id | relationship_name | relationship_type | category | confidence_baseline
  
-- 4. 实体关系
entity_relationships
  id | source_entity_id | target_entity_id | relationship_type_id | confidence
  
-- 5. 处理统计
processing_statistics
  id | document_id | formulas_count | herbs_count | graph_density
  
-- 6. 质量指标
quality_metrics
  id | document_id | confidence_score | completeness | entity_precision
  
-- 7. 研究分析
research_analyses
  id | document_id | research_perspectives (JSONB) | formula_comparisons | ...
  
-- 8. 处理日志
processing_logs
  id | document_id | module_name | status | execution_time_ms
```

**合计**：8张表，50+个字段，预留JSONB用于灵活扩展

### Neo4j 图结构一览

```cypher
节点类型: Formula, Herb, Syndrome, Efficacy
关系类型: SOVEREIGN, MINISTER, ASSISTANT, ENVOY, TREATS, HAS_EFFICACY, SIMILAR_TO, CONTAINS
```

---

## 🔌 快速启动指南

### 前置条件检查表

```bash
□ Windows 10/11 系统
□ PostgreSQL 14+ 已安装
□ Neo4j 5.26+ 已安装（D:\neo4j-community-5.26.23-windows）
□ Python 3.8+ 已安装
□ Git 已安装（用于克隆项目）
```

### 3步启动

#### 第1步：安装Python依赖

```bash
pip install -r requirements.txt

# 新增依赖（如果requirements.txt未更新）
pip install psycopg2-binary>=2.9.0,<3.0
pip install sqlalchemy>=2.0,<3.0
pip install neo4j>=5.0,<6.0
```

#### 第2步：初始化数据库

```bash
# 创建PostgreSQL数据库
psql -U postgres
  CREATE DATABASE tcm_autoresearch;
  CREATE USER tcm_user WITH PASSWORD 'password';
  GRANT ALL ON DATABASE tcm_autoresearch TO tcm_user;
  \q

# 启动Neo4j（在D:\neo4j-community-5.26.23-windows）
  bin\neo4j.exe console
```

#### 第3步：初始化存储系统

```bash
# 创建初始化脚本 init_storage.py
python -c "
from src.storage import UnifiedStorageDriver
storage = UnifiedStorageDriver(
    'postgresql://tcm_user:password@localhost:5432/tcm_autoresearch',
    'neo4j://localhost:7687',
    ('neo4j', 'password')
)
storage.initialize()
print('✅ 存储系统初始化完成')
"
```

---

## 📈 预期性能指标

| 操作 | 时间 | 操作对象 |
|------|------|--------|
| 单文档入库 | <2秒 | 500个实体 |
| 批量查询 | <100ms | 按索引查询 |
| 路径查询 | <200ms | 3层关系遍历 |
| 统计分析 | <500ms | 全库聚合 |

---

## 🎓 学习路径

### 对于项目管理者

1. 阅读 [STORAGE_PLAN_SUMMARY.md](STORAGE_PLAN_SUMMARY.md) - 3分钟
2. 浏览 [STORAGE_ARCHITECTURE.md](STORAGE_ARCHITECTURE.md) 第1-3章 - 10分钟
3. 了解成本、时间、风险 - 5分钟

**总耗时**：18分钟

### 对于开发工程师

1. 学习 [STORAGE_ARCHITECTURE.md](STORAGE_ARCHITECTURE.md) 全文 - 30分钟
2. 按照 [STORAGE_DEPLOYMENT.md](STORAGE_DEPLOYMENT.md) 部署 - 1小时
3. 运行 [STORAGE_QUERIES.md](STORAGE_QUERIES.md) 中的示例 - 30分钟
4. 阅读 [STORAGE_INTEGRATION.md](STORAGE_INTEGRATION.md) - 30分钟
5. 修改 run_cycle_demo.py 并测试 - 1小时

**总耗时**：3.5小时

### 对于测试人员

1. 部署环境（按部署指南）- 1小时
2. 运行 test_storage_integration.py - 15分钟
3. 验证数据一致性（SQL查询）- 30分钟
4. 负载测试 - 1小时

**总耗时**：2.75小时

---

## 🛠️ 故障排除快速入门

| 问题 | 错误信息 | 解决方案 |
|------|--------|--------|
| PostgreSQL连接失败 | `psycopg2.OperationalError` | 检查：主机、端口、用户名、密码、防火墙 |
| Neo4j认证失败 | `AuthError: unauthorized` | 检查Neo4j服务启动状态，确认密码 |
| 创建表失败 | `relation already exists` | 清空数据库后重试 |
| 内存溢出 | `MemoryError` | 增加池大小配置 |
| 数据不一致 | 行数不匹配 | 检查日志表，找到失败模块，手动同步 |

详见 [STORAGE_DEPLOYMENT.md](STORAGE_DEPLOYMENT.md) 故障排除章节

---

## 📞 技术支持

### 文档查询

```
问题类型              查询文档
────────────────────────────────────────
架构问题          → STORAGE_ARCHITECTURE.md
部署问题          → STORAGE_DEPLOYMENT.md
查询方法          → STORAGE_QUERIES.md
集成问题          → STORAGE_INTEGRATION.md
方案总览          → STORAGE_PLAN_SUMMARY.md
```

### 代码调试

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 连接测试
from src.storage import UnifiedStorageDriver
storage = UnifiedStorageDriver(...)
storage.initialize()
print(storage.get_storage_statistics())
```

---

## 📋 验收标准检查表

- [ ] 所有5个Python模块正确导入
- [ ] PostgreSQL 8张表成功创建
- [ ] Neo4j 默认关系类型预置完成
- [ ] 示例文档入库成功
- [ ] SQL查询返回正确结果
- [ ] Cypher查询返回正确结果
- [ ] 数据一致性检查通过
- [ ] 所有单元测试通过
- [ ] 完整集成测试通过
- [ ] 备份恢复脚本验证

---

## 📦 版本信息

- **方案版本**：v1.0
- **创建日期**：2026-03-28
- **最后更新**：2026-03-28
- **状态**：✅ 完整设计交付

---

## 📄 许可证

MIT License - 符合 T/C IATCM 098-2023 标准

---

**🎉 项目交付完成！**

所有设计、代码、文档已完成。下一步：

1. **审核文档** - 确认架构符合需求
2. **部署测试** - 在D盘Neo4j和本地PostgreSQL验证
3. **集成开发** - 修改run_cycle_demo.py集成到系统
4. **压力测试** - 验证生产环境性能
5. **上线发布** - 迁移现有数据到新系统

