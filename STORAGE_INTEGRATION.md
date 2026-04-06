# 存储系统集成指南

## 概述

本指南说明如何将统一存储驱动（PostgreSQL + Neo4j）集成到中医古籍研究系统的现有处理流程中。

---

## 架构集成概图

```
输入文件
   ↓
┌─────────────────────────────────────┐
│   修改后的处理流程                   │
├─────────────────────────────────────┤
│                                     │
│ 1. DocumentPreprocessor             │
│    └→ save_document()               │
│    └→ log_module_execution()        │
│                                     │
│ 2. AdvancedEntityExtractor          │
│    └→ save_entities()               │
│    └→ log_module_execution()        │
│                                     │
│ 3. SemanticGraphBuilder             │
│    ├→ save_entities()               │
│    ├→ save_relationships()          │
│    ├→ save_statistics()             │
│    └→ log_module_execution()        │
│                                     │
│ 4. ReasoningEngine                  │
│    └→ log_module_execution()        │
│                                     │
│ 5. OutputGenerator                  │
│    ├→ save_research_analysis()      │
│    ├→ save_quality_metrics()        │
│    ├→ update_document_status()      │
│    └→ log_module_execution()        │
│                                     │
└─────────────────────────────────────┘
   ↓
┌──────────────────┐  ┌─────────────────┐
│  PostgreSQL      │  │   Neo4j         │
│  结构化数据      │  │   图数据        │
└──────────────────┘  └─────────────────┘
```

---

## 第一步：配置config.yml

```yaml
# config.yml

# 系统基本信息（保持不变）
system:
  name: "中医古籍全自动研究系统"
  version: "2.0.0"

# 新增：存储系统配置
storage:
  enabled: true
  
  postgresql:
    host: localhost
    port: 5432
    database: tcm_autoresearch
    user: tcm_user
    password: ${DB_PASSWORD}
    pool_size: 10
    max_overflow: 20
  
  neo4j:
    uri: neo4j://localhost:7687
    user: neo4j
    password: ${NEO4J_PASSWORD}
    database: neo4j

# 模块配置（保持现有配置不变，新增存储相关选项）
modules:
  document_preprocessing:
    enabled: true
    # ... 现有配置 ...
    storage_enabled: true  # 新增
  
  entity_extraction:
    enabled: true
    # ... 现有配置 ...
    storage_enabled: true  # 新增
  
  semantic_modeling:
    enabled: true
    # ... 现有配置 ...
    storage_enabled: true  # 新增
```

---

## 第二步：修改主处理循环

### 文件：run_cycle_demo.py

```python
#!/usr/bin/env python3
"""
中医古籍全自动研究系统 - 集成存储版本
"""

import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path

# 导入存储模块
from src.storage import UnifiedStorageDriver
from src.analysis.entity_extractor import AdvancedEntityExtractor
from src.output.output_generator import OutputGenerator
from src.analysis.preprocessor import DocumentPreprocessor
from src.analysis.reasoning_engine import ReasoningEngine
from src.analysis.semantic_graph import SemanticGraphBuilder

logger = logging.getLogger(__name__)


class EnhancedIterationCycle:
    """
    增强的迭代循环 - 集成存储支持
    """
    
    def __init__(self, config, storage_driver=None):
        self.config = config
        self.storage = storage_driver
        
        # 初始化处理模块
        self.modules = [
            ("DocumentPreprocessor", DocumentPreprocessor()),
            ("AdvancedEntityExtractor", AdvancedEntityExtractor()),
            ("SemanticGraphBuilder", SemanticGraphBuilder()),
            ("ReasoningEngine", ReasoningEngine()),
            ("OutputGenerator", OutputGenerator()),
        ]
    
    def execute_with_storage(self, source_file: str, raw_text: str) -> dict:
        """
        执行完整处理流程，包含存储
        
        Args:
            source_file: 源文件路径
            raw_text: 原始文本内容
        
        Returns:
            处理结果
        """
        
        # 第0步：保存文档元信息
        if self.storage:
            doc_id = self.storage.save_document(
                source_file=source_file,
                objective="automatic_analysis",
                raw_text_size=len(raw_text)
            )
            self.storage.log_module_execution(
                doc_id, 'IterationCycle', 'start',
                message=f"开始处理: {source_file}"
            )
        else:
            doc_id = None
        
        context = {
            "source_file": source_file,
            "raw_text": raw_text,
            "document_id": doc_id,
            "statistics": {}
        }
        
        # 第1步：文档预处理
        try:
            module_name = "DocumentPreprocessor"
            start_time = time.time()
            
            preprocessor = self.modules[0][1]
            initialized = preprocessor.initialize()
            if not initialized:
                raise RuntimeError("DocumentPreprocessor 初始化失败")
            
            result = preprocessor.execute(context)
            context.update(result)
            
            exec_time = int((time.time() - start_time) * 1000)
            if self.storage and doc_id:
                self.storage.log_module_execution(
                    doc_id, module_name, 'success',
                    execution_time_ms=exec_time
                )
            logger.info(f"{module_name} 完成 ({exec_time}ms)")
        
        except Exception as e:
            logger.error(f"{module_name} 失败: {e}")
            if self.storage and doc_id:
                self.storage.log_module_execution(
                    doc_id, module_name, 'failure',
                    error_details=str(e)
                )
            raise
        
        # 第2步：实体抽取（新增存储）
        try:
            module_name = "AdvancedEntityExtractor"
            start_time = time.time()
            
            extractor = self.modules[1][1]
            initialized = extractor.initialize()
            if not initialized:
                raise RuntimeError("AdvancedEntityExtractor 初始化失败")
            
            result = extractor.execute(context)
            context.update(result)
            entities = result.get("entities", [])
            
            # ★ 保存实体到存储
            if self.storage and doc_id and entities:
                self.storage.save_entities(doc_id, entities)
            
            exec_time = int((time.time() - start_time) * 1000)
            if self.storage and doc_id:
                self.storage.log_module_execution(
                    doc_id, module_name, 'success',
                    execution_time_ms=exec_time
                )
            logger.info(f"{module_name} 完成 ({exec_time}ms, {len(entities)} 个实体)")
        
        except Exception as e:
            logger.error(f"{module_name} 失败: {e}")
            if self.storage and doc_id:
                self.storage.log_module_execution(
                    doc_id, module_name, 'failure',
                    error_details=str(e)
                )
            raise
        
        # 第3步：语义建模（新增存储）
        try:
            module_name = "SemanticGraphBuilder"
            start_time = time.time()
            
            modeler = self.modules[2][1]
            initialized = modeler.initialize()
            if not initialized:
                raise RuntimeError("SemanticGraphBuilder 初始化失败")
            
            result = modeler.execute(context)
            context.update(result)
            
            # 提取关系数据
            graph_data = result.get("semantic_graph", {})
            edges = graph_data.get("edges", [])
            
            # ★ 保存关系到存储
            if self.storage and doc_id and edges:
                # 转换边格式为关系格式
                relationships = []
                for edge in edges:
                    relationships.append({
                        'source_entity_id': edge['source'],
                        'target_entity_id': edge['target'],
                        'relationship_type': edge.get('attributes', {}).get('relationship_type', 'unknown'),
                        'confidence': edge.get('attributes', {}).get('confidence', 0.5),
                        'created_by_module': module_name
                    })
                self.storage.save_relationships(doc_id, relationships)
            
            # ★ 保存统计信息
            graph_stats = result.get("graph_statistics", {})
            if self.storage and doc_id and graph_stats:
                stats_data = {
                    'formulas_count': len([e for e in entities if e.get('type') == 'formula']),
                    'herbs_count': len([e for e in entities if e.get('type') == 'herb']),
                    'syndromes_count': len([e for e in entities if e.get('type') == 'syndrome']),
                    'efficacies_count': len([e for e in entities if e.get('type') == 'efficacy']),
                    'relationships_count': len(edges),
                    'graph_nodes_count': graph_stats.get('nodes_count', 0),
                    'graph_edges_count': graph_stats.get('edges_count', 0),
                    'graph_density': graph_stats.get('density', 0),
                    'connected_components': graph_stats.get('connected_components', 0),
                    'source_modules': ['DocumentPreprocessor', 'EntityExtractor', 'SemanticGraphBuilder'],
                    'processing_time_ms': int((time.time() - start_time) * 1000)
                }
                self.storage.save_statistics(doc_id, stats_data)
            
            exec_time = int((time.time() - start_time) * 1000)
            if self.storage and doc_id:
                self.storage.log_module_execution(
                    doc_id, module_name, 'success',
                    execution_time_ms=exec_time
                )
            logger.info(f"{module_name} 完成 ({exec_time}ms)")
        
        except Exception as e:
            logger.error(f"{module_name} 失败: {e}")
            if self.storage and doc_id:
                self.storage.log_module_execution(
                    doc_id, module_name, 'failure',
                    error_details=str(e)
                )
            raise
        
        # 第4步：推理分析
        try:
            module_name = "ReasoningEngine"
            start_time = time.time()
            
            reasoner = self.modules[3][1]
            initialized = reasoner.initialize()
            if not initialized:
                raise RuntimeError("ReasoningEngine 初始化失败")
            
            result = reasoner.execute(context)
            context.update(result)
            
            exec_time = int((time.time() - start_time) * 1000)
            if self.storage and doc_id:
                self.storage.log_module_execution(
                    doc_id, module_name, 'success',
                    execution_time_ms=exec_time
                )
            logger.info(f"{module_name} 完成 ({exec_time}ms)")
        
        except Exception as e:
            logger.error(f"{module_name} 失败: {e}")
            if self.storage and doc_id:
                self.storage.log_module_execution(
                    doc_id, module_name, 'failure',
                    error_details=str(e)
                )
            raise
        
        # 第5步：输出生成和最终存储
        try:
            module_name = "OutputGenerator"
            start_time = time.time()
            
            generator = self.modules[4][1]
            initialized = generator.initialize()
            if not initialized:
                raise RuntimeError("OutputGenerator 初始化失败")
            
            result = generator.execute(context)
            context.update(result)
            
            # ★ 保存质量指标
            quality_metrics = context.get("quality_metrics", {})
            if self.storage and doc_id and quality_metrics:
                self.storage.save_quality_metrics(doc_id, quality_metrics)
            
            # ★ 保存研究分析
            research_analysis = {
                'research_perspectives': context.get('research_perspectives', {}),
                'formula_comparisons': context.get('formula_comparisons', {}),
                'herb_properties_analysis': context.get('herb_properties', {}),
                'pharmacology_integration': context.get('pharmacology_integration', {}),
                'summary_analysis': context.get('summary_analysis', {}),
            }
            if self.storage and doc_id:
                self.storage.save_research_analysis(doc_id, research_analysis)
            
            # ★ 更新文档状态
            if self.storage and doc_id:
                self.storage.update_document_status(doc_id, 'completed')
                self.storage.log_module_execution(
                    doc_id, module_name, 'success',
                    execution_time_ms=int((time.time() - start_time) * 1000)
                )
            
            logger.info(f"{module_name} 完成")
        
        except Exception as e:
            logger.error(f"{module_name} 失败: {e}")
            if self.storage and doc_id:
                self.storage.update_document_status(doc_id, 'failed')
                self.storage.log_module_execution(
                    doc_id, module_name, 'failure',
                    error_details=str(e)
                )
            raise
        
        return context


def main():
    """主函数"""
    import yaml
    
    # 加载配置
    with open('config.yml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 初始化存储驱动（如果启用）
    storage = None
    if config.get('storage', {}).get('enabled', False):
        db_config = config['storage']['postgresql']
        neo4j_config = config['storage']['neo4j']
        
        pg_url = (
            f"postgresql://{db_config['user']}:{os.getenv('DB_PASSWORD')}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        )
        neo4j_uri = neo4j_config['uri']
        neo4j_auth = (neo4j_config['user'], os.getenv('NEO4J_PASSWORD'))
        
        storage = UnifiedStorageDriver(pg_url, neo4j_uri, neo4j_auth)
        storage.initialize()
        logger.info("存储驱动已初始化")
    
    # 创建处理循环
    cycle = EnhancedIterationCycle(config, storage)
    
    # 处理示例文件
    example_text = "小柴胡汤方：柴胡半斤，黄芩三两，人参三两，甘草三两，半夏半升，生姜三两，大枣十二枚。"
    
    try:
        result = cycle.execute_with_storage('test_document.txt', example_text)
        logger.info(f"处理完成！结果包含 {len(result.get('entities', []))} 个实体")
        
        if storage:
            stats = storage.get_storage_statistics()
            logger.info(f"存储统计: {stats}")
    
    finally:
        if storage:
            storage.close()


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    main()
```

---

## 第三步：环境变量配置

创建 `.env` 文件（放在项目根目录）：

```bash
# .env
DB_PASSWORD=your_postgres_password
NEO4J_PASSWORD=your_neo4j_password
```

或在 PowerShell 中设置：

```powershell
$env:DB_PASSWORD = "your_postgres_password"
$env:NEO4J_PASSWORD = "your_neo4j_password"
```

---

## 第四步：测试集成

创建测试脚本 `test_storage_integration.py`：

```python
#!/usr/bin/env python3
"""存储集成测试"""

import os
import sys
from pathlib import Path

# 设置路径
sys.path.insert(0, str(Path(__file__).parent))

from src.storage import UnifiedStorageDriver
from run_cycle_demo import EnhancedIterationCycle

def test_storage_integration():
    """测试存储集成"""
    
    # 初始化存储
    print("初始化存储系统...")
    storage = UnifiedStorageDriver(
        'postgresql://tcm_user:password@localhost:5432/tcm_autoresearch',
        'neo4j://localhost:7687',
        ('neo4j', 'password')
    )
    storage.initialize()
    
    # 创建处理循环
    config = {'storage': {'enabled': True}}
    cycle = EnhancedIterationCycle(config, storage)
    
    # 测试数据
    test_doc = "小柴胡汤由柴胡、黄芩、人参组成，主治少阳症。"
    
    # 执行处理
    print("执行处理流程...")
    result = cycle.execute_with_storage('test_doc.txt', test_doc)
    
    # 验证结果
    print(f"实体数: {len(result.get('entities', []))}")
    print(f"关系数: {len(result.get('relationships', []))}")
    
    # 查询验证
    print("\n验证存储数据...")
    stats = storage.get_storage_statistics()
    print(f"PostgreSQL 文档: {stats['postgresql']['documents']}")
    print(f"Neo4j 节点: {stats['neo4j']['total_nodes']}")
    
    storage.close()
    print("✅ 测试完成")

if __name__ == '__main__':
    test_storage_integration()
```

运行测试：

```bash
python test_storage_integration.py
```

---

## 第五步：部署检查清单

- [ ] PostgreSQL 已安装并运行
- [ ] Neo4j 已安装并运行
- [ ] requirements.txt 已更新 (`psycopg2-binary`, `sqlalchemy`, `neo4j`)
- [ ] config.yml 已配置存储部分
- [ ] 环境变量已设置（DB_PASSWORD, NEO4J_PASSWORD）
- [ ] 数据库和用户已创建
- [ ] 运行了初始化脚本
- [ ] 存储模块单元测试通过
- [ ] 集成测试成功完成
- [ ] 备份脚本已部署

---

## 故障排除

### 连接失败

```python
# 测试 PostgreSQL 连接
from sqlalchemy import create_engine
engine = create_engine('postgresql://user:password@localhost:5432/db')
connection = engine.connect()
print("✅ PostgreSQL 连接成功")
connection.close()
```

### Neo4j 连接失败

```python
from src.storage import Neo4jDriver
neo4j = Neo4jDriver('neo4j://localhost:7687', ('neo4j', 'password'))
neo4j.connect()
print("✅ Neo4j 连接成功")
neo4j.close()
```

### 数据不同步

```python
# 检查数据一致性
from src.storage import UnifiedStorageDriver
storage = UnifiedStorageDriver(...)
storage.initialize()
stats = storage.get_storage_statistics()
print(stats)
storage.close()
```

---

## 后续优化

1. **性能优化**：添加批量写入、异步操作
2. **容错机制**：实现重试逻辑、降级策略
3. **监控告警**：添加存储系统健康检查
4. **数据验证**：实现数据一致性检查和修复
5. **分析报表**：创建存储利用率和性能报告

