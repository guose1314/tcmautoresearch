# 存储系统查询和使用示例

## PostgreSQL 常用查询

### 1. 文档管理查询

```sql
-- 查询所有文档及其状态
SELECT id, source_file, process_status, quality_score, 
       entities_extracted_count, processing_timestamp
FROM documents
ORDER BY processing_timestamp DESC;

-- 查询处理失败的文档
SELECT * FROM documents 
WHERE process_status = 'failed'
ORDER BY processing_timestamp DESC;

-- 统计各状态的文档数
SELECT process_status, COUNT(*) as count
FROM documents
GROUP BY process_status;
```

### 2. 实体查询

```sql
-- 统计各类型实体数量
SELECT type, COUNT(*) as count, AVG(confidence) as avg_confidence
FROM entities
GROUP BY type
ORDER BY count DESC;

-- 查询高置信度实体
SELECT name, type, confidence, document_id
FROM entities
WHERE confidence >= 0.8
ORDER BY confidence DESC;

-- 查询特定文档的实体
SELECT name, type, confidence, position, length
FROM entities
WHERE document_id = 'document_id_here'
ORDER BY position;

-- 查询特定类型的实体
SELECT name, confidence, COUNT(DISTINCT document_id) as doc_count
FROM entities
WHERE type = 'formula'
GROUP BY name, confidence
ORDER BY doc_count DESC;
```

### 3. 关系查询

```sql
-- 统计关系分布
SELECT rt.relationship_name, COUNT(er.id) as count,
       AVG(er.confidence) as avg_confidence
FROM relationship_types rt
LEFT JOIN entity_relationships er ON rt.id = er.relationship_type_id
GROUP BY rt.id, rt.relationship_name
ORDER BY count DESC;

-- 查询特定实体的所有关系
SELECT 
    e1.name as source_name, e1.type as source_type,
    rt.relationship_name,
    e2.name as target_name, e2.type as target_type,
    er.confidence
FROM entity_relationships er
JOIN entities e1 ON er.source_entity_id = e1.id
JOIN entities e2 ON er.target_entity_id = e2.id
JOIN relationship_types rt ON er.relationship_type_id = rt.id
WHERE e1.id = 'entity_id_here'
ORDER BY er.confidence DESC;

-- 查询高置信度关系
SELECT 
    e1.name as source, e2.name as target,
    rt.relationship_name, er.confidence
FROM entity_relationships er
JOIN entities e1 ON er.source_entity_id = e1.id
JOIN entities e2 ON er.target_entity_id = e2.id
JOIN relationship_types rt ON er.relationship_type_id = rt.id
WHERE er.confidence >= 0.85
ORDER BY er.confidence DESC
LIMIT 100;
```

### 4. 统计查询

```sql
-- 获取文档处理统计
SELECT 
    d.source_file,
    ps.formulas_count,
    ps.herbs_count,
    ps.syndromes_count,
    ps.relationships_count,
    ps.graph_density,
    ps.processing_time_ms
FROM documents d
LEFT JOIN processing_statistics ps ON d.id = ps.document_id
ORDER BY d.processing_timestamp DESC;

-- 查询处理统计摘要
SELECT 
    COUNT(DISTINCT d.id) as total_documents,
    SUM(ps.formulas_count) as total_formulas,
    SUM(ps.herbs_count) as total_herbs,
    SUM(ps.syndromes_count) as total_syndromes,
    AVG(ps.graph_density) as avg_graph_density,
    AVG(d.quality_score) as avg_quality
FROM documents d
LEFT JOIN processing_statistics ps ON d.id = ps.document_id;
```

### 5. 质量指标查询

```sql
-- 查询质量不达标的文档
SELECT d.source_file, qm.confidence_score, qm.completeness,
       qm.entity_precision, qm.relationship_precision
FROM documents d
JOIN quality_metrics qm ON d.id = qm.document_id
WHERE qm.confidence_score < 0.70
ORDER BY qm.confidence_score;

-- 查询质量指标分布
SELECT 
    CASE 
        WHEN confidence_score >= 0.9 THEN 'Excellent'
        WHEN confidence_score >= 0.8 THEN 'Good'
        WHEN confidence_score >= 0.7 THEN 'Fair'
        ELSE 'Poor'
    END as quality_level,
    COUNT(*) as count
FROM quality_metrics
GROUP BY quality_level;
```

### 6. 日志查询

```sql
-- 查询最近的处理日志
SELECT module_name, status, message, timestamp
FROM processing_logs
WHERE document_id = 'document_id_here'
ORDER BY timestamp DESC
LIMIT 50;

-- 统计模块错误
SELECT module_name, status, COUNT(*) as count
FROM processing_logs
WHERE status = 'failure'
GROUP BY module_name, status
ORDER BY count DESC;

-- 查询处理时间
SELECT module_name, AVG(execution_time_ms) as avg_time_ms,
       MAX(execution_time_ms) as max_time_ms,
       COUNT(*) as runs
FROM processing_logs
WHERE status = 'success'
GROUP BY module_name
ORDER BY avg_time_ms DESC;
```

---

## Neo4j 查询示例

### 1. 基本查询

```cypher
-- 查询所有节点
MATCH (n) RETURN n LIMIT 100;

-- 按类型统计节点
MATCH (n) RETURN labels(n)[0] as label, count(*) as count;

-- 查询所有关系类型
MATCH ()-[r]->() RETURN type(r) as relationship, count(*) as count;
```

### 2. 方剂查询

```cypher
-- 查询特定方剂的完整组成
MATCH (f:Formula {name: '小柴胡汤'})
OPTIONAL MATCH (f)-[r]->(h:Herb)
WHERE type(r) IN ['SOVEREIGN', 'MINISTER', 'ASSISTANT', 'ENVOY']
WITH f, collect(DISTINCT {role: type(r), herb: h.name}) AS role_pairs
RETURN f,
       [pair IN role_pairs WHERE pair.role = 'SOVEREIGN' AND pair.herb IS NOT NULL | pair.herb] AS sovereign_herbs,
       [pair IN role_pairs WHERE pair.role = 'MINISTER' AND pair.herb IS NOT NULL | pair.herb] AS minister_herbs,
       [pair IN role_pairs WHERE pair.role = 'ASSISTANT' AND pair.herb IS NOT NULL | pair.herb] AS assistant_herbs,
       [pair IN role_pairs WHERE pair.role = 'ENVOY' AND pair.herb IS NOT NULL | pair.herb] AS envoy_herbs;

-- 查询包含特定中药的所有方剂
MATCH (h:Herb {name: '柴胡'})<-[:SOVEREIGN|MINISTER|ASSISTANT|ENVOY]-(f:Formula)
RETURN f.name as formula, count(*) as formulas;
```

说明：这里推荐使用“单次 OPTIONAL MATCH + type(r) 过滤”的写法，避免像旧版四段式 OPTIONAL MATCH 那样在图中缺少某个关系类型时产生无意义的 Neo4j 通知噪音。

### 3. 症候查询

```cypher
-- 查询能治疗特定症候的方剂
MATCH (f:Formula)-[:TREATS]->(s:Syndrome {name: '少阳驸绿'})
RETURN f.name as formula, f.confidence as confidence
ORDER BY confidence DESC;

-- 查询方剂治疗的症候
MATCH (f:Formula {name: '小柴胡汤'})-[:TREATS]->(s:Syndrome)
RETURN s.name as syndrome, s as properties;
```

### 4. 中药查询

```cypher
-- 查询中药的功效
MATCH (h:Herb {name: '黄芩'})-[:HAS_EFFICACY]->(e:Efficacy)
RETURN e.name as efficacy;

-- 统计各功效的中药数量
MATCH (h:Herb)-[:HAS_EFFICACY]->(e:Efficacy)
RETURN e.name as efficacy, count(h) as herb_count
ORDER BY herb_count DESC;
```

### 5. 路径分析

```cypher
-- 查询从方剂到症候的完整路径
MATCH p = (f:Formula {name: '小柴胡汤'})-[*]->(s:Syndrome)
RETURN p;

-- 查询中药的所有相关信息
MATCH (h:Herb {name: '柴胡'})
OPTIONAL MATCH (h)<-[:SOVEREIGN|MINISTER|ASSISTANT|ENVOY]-(f:Formula)
OPTIONAL MATCH (h)-[:HAS_EFFICACY]->(e:Efficacy)
OPTIONAL MATCH (f)-[:TREATS]->(s:Syndrome)
RETURN h, collect(distinct f) as formulas,
       collect(distinct e) as efficacies,
       collect(distinct s) as syndromes;
```

### 6. 高级分析

```cypher
-- 查询中心性（最重要的中药）
MATCH (h:Herb)
WITH h, size((h)<-[:SOVEREIGN|MINISTER|ASSISTANT|ENVOY]-()) as in_degree,
     size((h)-[:HAS_EFFICACY]->()) as out_degree
RETURN h.name as herb, in_degree, out_degree, (in_degree + out_degree) as total_degree
ORDER BY total_degree DESC
LIMIT 20;

-- 查询相似方剂的聚类
MATCH (f1:Formula)-[:SIMILAR_TO]-(f2:Formula)
RETURN f1.name, f2.name, f1.confidence
LIMIT 50;

-- 查询功效相关的中药组合
MATCH (h1:Herb)-[:HAS_EFFICACY]->(e:Efficacy)<-[:HAS_EFFICACY]-(h2:Herb)
WHERE h1.name < h2.name
WITH h1, h2, e, count(*) as shared_efficacies
WHERE shared_efficacies > 1
RETURN h1.name as herb1, h2.name as herb2, shared_efficacies, collect(e.name) as efficacies
ORDER BY shared_efficacies DESC;
```

---

## Python 使用示例

### 示例1：初始化和基本操作

```python
from src.storage import UnifiedStorageDriver
from uuid import uuid4

# 初始化存储驱动
storage = UnifiedStorageDriver(
    'postgresql://tcm_user:password@localhost:5432/tcm_autoresearch',
    'neo4j://localhost:7687',
    ('neo4j', 'password')
)
storage.initialize()

# 保存文档
doc_id = storage.save_document(
    source_file='path/to/document.txt',
    objective='analyze_formula_composition'
)

print(f"文档已保存: {doc_id}")

# 保存实体
entities = [
    {
        'name': '小柴胡汤',
        'type': 'formula',
        'confidence': 0.95,
        'position': 100,
        'length': 4
    },
    {
        'name': '柴胡',
        'type': 'herb',
        'confidence': 0.92,
        'position': 100,
        'length': 2
    }
]

entity_ids = storage.save_entities(doc_id, entities)
print(f"实体已保存: {entity_ids}")

# 保存关系
relationships = [
    {
        'source_entity_id': entity_ids[0],  # 小柴胡汤
        'target_entity_id': entity_ids[1],  # 柴胡
        'relationship_type': 'SOVEREIGN',
        'confidence': 0.95,
        'created_by_module': 'semantic_graph_builder'
    }
]

rel_ids = storage.save_relationships(doc_id, relationships)
print(f"关系已保存: {rel_ids}")

storage.close()
```

### 示例2：复杂查询

```python
from src.storage import UnifiedStorageDriver

storage = UnifiedStorageDriver(...)
storage.initialize()

# 查询方剂组成
composition = storage.query_formula_composition('小柴胡汤')
print("方剂组成（君臣佐使）:")
for role, herbs in composition.items():
    print(f"  {role}: {', '.join(herbs)}")

# 查询治疗同一症候的方剂
formulas = storage.query_treating_formulas('少阳上热')
print(f"\n治疗'少阳上热'的方剂:")
for formula in formulas:
    print(f"  - {formula['name']}: 置信度 {formula['properties'].get('confidence', 0)}")

# 获取存储系统统计
stats = storage.get_storage_statistics()
print(f"\n存储系统统计:")
print(f"PostgreSQL:")
print(f"  文档: {stats['postgresql']['documents']}")
print(f"  实体: {stats['postgresql']['entities']}")
print(f"  关系: {stats['postgresql']['relationships']}")
print(f"\nNeo4j:")
print(f"  总节点: {stats['neo4j']['total_nodes']}")
print(f"  总关系: {stats['neo4j']['total_relationships']}")

storage.close()
```

### 示例3：集成到现有处理流程

```python
from src.storage import UnifiedStorageDriver
from src.cycle.cycle_runner import execute_real_module_pipeline

# 初始化存储
storage = UnifiedStorageDriver(...)
storage.initialize()

# 处理文档
doc_id = storage.save_document(source_file)
storage.log_module_execution(doc_id, 'DocumentPreprocessor', 'start')

try:
    module_results = execute_real_module_pipeline(
        {
            "source_file": source_file,
            "raw_text": document_content,
            "document_id": doc_id,
        }
    )
    final_context = module_results[-1]["input_data"] if module_results else {}
    
    # 保存结果到存储
    storage.save_entities(doc_id, final_context.get('entities', []))
    storage.save_relationships(
        doc_id,
        final_context.get('relationships', final_context.get('semantic_relationships', [])),
    )
    storage.save_statistics(doc_id, final_context.get('statistics', {}))
    
    storage.log_module_execution(doc_id, 'Complete', 'success')
    storage.update_document_status(doc_id, 'completed')
    
except Exception as e:
    storage.log_module_execution(
        doc_id, 'Complete', 'failure',
        error_details=str(e)
    )
    storage.update_document_status(doc_id, 'failed')

storage.close()
```

### 示例4：数据验证和同步

```python
from src.storage import UnifiedStorageDriver, Neo4jDriver

storage = UnifiedStorageDriver(...)
storage.initialize()

# 验证PostgreSQL和Neo4j的数据一致性
pg_stats = storage.session.query(
    func.count(distinct(Entity.id))
).scalar()

neo4j_stats = storage.neo4j.get_graph_statistics()

print(f"PostgreSQL 实体数: {pg_stats}")
print(f"Neo4j 节点数: {neo4j_stats['total_nodes']}")

if pg_stats != neo4j_stats['total_nodes']:
    print("警告：数据可能不一致！")
    # 可以实现同步逻辑

storage.close()
```

---

## 维护脚本

### 1. 数据库备份脚本

```python
#!/usr/bin/env python3
"""自动备份脚本"""

import subprocess
from datetime import datetime
from pathlib import Path

def backup_postgresql():
    """备份PostgreSQL"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f'backup_postgres_{timestamp}.sql'
    
    cmd = [
        'pg_dump',
        '-U', 'tcm_user',
        '-d', 'tcm_autoresearch',
        '-f', backup_file
    ]
    
    subprocess.run(cmd, check=True)
    print(f"PostgreSQL 备份完成: {backup_file}")

def backup_neo4j():
    """备份Neo4j"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f'backup_neo4j_{timestamp}.dump'
    
    cmd = [
        'neo4j-admin',
        'database',
        'dump',
        'neo4j',
        backup_file
    ]
    
    subprocess.run(cmd, check=True)
    print(f"Neo4j 备份完成: {backup_file}")

if __name__ == '__main__':
    backup_postgresql()
    backup_neo4j()
```

### 2. 数据一致性检查脚本

```python
#!/usr/bin/env python3
"""数据一致性检查脚本"""

from src.storage import UnifiedStorageDriver, Entity
from sqlalchemy import func

def check_consistency():
    """检查数据一致性"""
    storage = UnifiedStorageDriver(...)
    storage.initialize()
    
    # PostgreSQL 统计
    doc_count = storage.session.query(func.count(Document.id)).scalar()
    entity_count = storage.session.query(func.count(Entity.id)).scalar()
    
    # Neo4j 统计  
    neo4j_stats = storage.neo4j.get_graph_statistics()
    
    print("数据一致性检查结果:")
    print(f"PostgreSQL 文档: {doc_count}")
    print(f"PostgreSQL 实体: {entity_count}")
    print(f"Neo4j 文档节点: {neo4j_stats['nodes_by_type'].get('Document', 0)}")
    print(f"Neo4j 实体节点: {neo4j_stats['total_nodes'] - neo4j_stats['nodes_by_type'].get('Document', 0)}")
    
    if entity_count != (neo4j_stats['total_nodes'] - neo4j_stats['nodes_by_type'].get('Document', 0)):
        print("⚠️ 警告: 实体数量不匹配！")
    else:
        print("✅ 数据一致性检查通过")
    
    storage.close()

if __name__ == '__main__':
    check_consistency()
```

