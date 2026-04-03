#!/usr/bin/env python3
"""
完整存储系统测试 - 小样本性能验证
支持数据库离线模式（仅验证模块可用性）
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from uuid import uuid4

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class StorageFullTest:
    """存储系统完整测试"""
    
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'mode': 'unknown',
            'phases': {},
            'timings': {},
            'success': False,
        }
        self.storage = None
    
    def print_header(self, title):
        """打印标题"""
        print(f"\n{'='*70}")
        print(f"  {title.center(66)}")
        print(f"{'='*70}\n")
    
    def log_success(self, msg):
        """记录成功消息"""
        print(f"  ✅ {msg}")
        logger.info(msg)
    
    def log_info(self, msg):
        """记录信息"""
        print(f"  ℹ️  {msg}")
        logger.info(msg)
    
    def log_warn(self, msg):
        """记录警告"""
        print(f"  ⚠️  {msg}")
        logger.warning(msg)
    
    def log_error(self, msg):
        """记录错误"""
        print(f"  ❌ {msg}")
        logger.error(msg)
    
    def test_module_imports(self):
        """测试1: 模块导入"""
        self.print_header("测试1: 模块可用性")
        
        start = time.time()
        try:
            from src.storage import (
                Document,
                Entity,
                EntityRelationship,
                EntityTypeEnum,
                ProcessStatusEnum,
                UnifiedStorageDriver,
            )
            
            self.log_success("core 模块导入")
            
            from src.storage.db_models import DatabaseManager
            self.log_success("db_models 模块导入")
            
            from src.storage.neo4j_driver import Neo4jDriver
            self.log_success("neo4j_driver 模块导入")
            
            from src.storage.storage_driver import UnifiedStorageDriver as USD
            self.log_success("storage_driver 模块导入")
            
            elapsed = int((time.time() - start) * 1000)
            self.results['phases']['module_imports'] = {
                'status': 'success',
                'time_ms': elapsed
            }
            self.results['timings']['module_imports'] = elapsed
            
            print(f"\n  ⏱️  导入耗时: {elapsed}ms")
            return True
            
        except Exception as e:
            self.log_error(f"模块导入失败: {e}")
            self.results['phases']['module_imports'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    def test_database_connection(self):
        """测试2: 数据库连接"""
        self.print_header("测试2: 数据库连接")
        
        start = time.time()
        
        try:
            from src.storage import UnifiedStorageDriver
            
            # 从环境读取连接参数
            db_password = os.getenv('DB_PASSWORD', 'password')
            neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')
            pg_host = os.getenv('DB_HOST', 'localhost')
            neo4j_host = os.getenv('NEO4J_HOST', 'localhost')
            
            pg_url = f"postgresql://tcm_user:{db_password}@{pg_host}:5432/tcm_autoresearch"
            neo4j_uri = f"neo4j://{neo4j_host}:7687"
            neo4j_auth = ("neo4j", neo4j_password)
            
            self.log_info(f"PostgreSQL: {pg_host}")
            self.log_info(f"Neo4j: {neo4j_host}")
            
            # 初始化存储驱动
            self.storage = UnifiedStorageDriver(pg_url, neo4j_uri, neo4j_auth)
            self.storage.initialize()
            
            self.log_success("数据库连接成功")
            self.results['mode'] = 'online'
            
            elapsed = int((time.time() - start) * 1000)
            self.results['phases']['database_connection'] = {
                'status': 'success',
                'time_ms': elapsed,
                'mode': 'online'
            }
            self.results['timings']['database_connection'] = elapsed
            
            print(f"\n  ⏱️  连接耗时: {elapsed}ms")
            return True
            
        except ConnectionRefusedError as e:
            self.log_warn(f"数据库连接被拒绝 (离线模式): {e}")
            self.results['mode'] = 'offline'
            self.results['phases']['database_connection'] = {
                'status': 'unavailable',
                'error': '数据库未运行'
            }
            return False
            
        except Exception as e:
            self.log_error(f"数据库连接失败: {e}")
            self.results['mode'] = 'offline'
            self.results['phases']['database_connection'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    def create_test_data(self):
        """创建小规模测试数据"""
        entities = [
            {'name': '小柴胡汤', 'type': 'formula', 'confidence': 0.95, 'position': 0, 'length': 4},
            {'name': '柴胡', 'type': 'herb', 'confidence': 0.98, 'position': 5, 'length': 2},
            {'name': '黄芩', 'type': 'herb', 'confidence': 0.95, 'position': 8, 'length': 2},
            {'name': '少阳症', 'type': 'syndrome', 'confidence': 0.90, 'position': 20, 'length': 3},
            {'name': '疏肝解郁', 'type': 'efficacy', 'confidence': 0.92, 'position': 30, 'length': 4},
        ]
        return entities
    
    def test_data_operations(self):
        """测试3: 数据操作"""
        if self.results['mode'] != 'online':
            self.print_header("测试3: 数据操作 (跳过 - 离线模式)")
            self.results['phases']['data_operations'] = {'status': 'skipped', 'reason': 'offline_mode'}
            return False
        
        self.print_header("测试3: 数据操作")
        
        try:
            start = time.time()
            
            # 创建文档
            doc_id = self.storage.save_document(
                f"test_doc_{str(uuid4())[:8]}",
                "performance_test",
                5000
            )
            self.log_success(f"创建文档: {doc_id}")
            
            # 创建实体
            entities_data = self.create_test_data()
            entity_ids = self.storage.save_entities(doc_id, entities_data)
            self.log_success(f"创建实体: {len(entity_ids)} 个")
            
            # 创建关系
            if len(entity_ids) >= 2:
                relationships = [
                    {
                        'source_entity_id': entity_ids[0],
                        'target_entity_id': entity_ids[1],
                        'relationship_type': 'SOVEREIGN',
                        'confidence': 0.95,
                        'created_by_module': 'test'
                    },
                    {
                        'source_entity_id': entity_ids[0],
                        'target_entity_id': entity_ids[3],
                        'relationship_type': 'TREATS',
                        'confidence': 0.85,
                        'created_by_module': 'test'
                    },
                ]
                rel_ids = self.storage.save_relationships(doc_id, relationships)
                self.log_success(f"创建关系: {len(rel_ids)} 个")
            
            # 保存统计
            stats = {
                'formulas_count': 1,
                'herbs_count': 2,
                'syndromes_count': 1,
                'efficacies_count': 1,
                'relationships_count': len(rel_ids) if len(entity_ids) >= 2 else 0,
                'graph_nodes_count': 5,
                'graph_edges_count': 2,
                'graph_density': 0.1,
                'connected_components': 1,
                'source_modules': ['test']
            }
            self.storage.save_statistics(doc_id, stats)
            self.log_success("保存统计数据")
            
            elapsed = int((time.time() - start) * 1000)
            self.results['phases']['data_operations'] = {
                'status': 'success',
                'entities': len(entity_ids),
                'relationships': len(rel_ids) if len(entity_ids) >= 2 else 0,
                'time_ms': elapsed
            }
            self.results['timings']['data_operations'] = elapsed
            
            print(f"\n  ⏱️  操作耗时: {elapsed}ms")
            return True
            
        except Exception as e:
            self.log_error(f"数据操作失败: {e}")
            self.results['phases']['data_operations'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    def run(self):
        """运行全部测试"""
        self.print_header("中医古籍研究 - 存储系统小样本测试")
        
        # 测试1: 模块导入 (必须)
        if not self.test_module_imports():
            self.log_error("模块导入失败，无法继续")
            return False
        
        # 测试2: 数据库连接 (可选)
        db_connected = self.test_database_connection()
        
        # 测试3: 数据操作 (仅在连接成功时执行)
        if db_connected:
            self.test_data_operations()
        else:
            self.print_header("测试3: 数据操作 (跳过 - 数据库未运行)")
            self.log_info("跳过数据库操作测试")
            self.results['phases']['data_operations'] = {
                'status': 'skipped',
                'reason': 'database_not_available'
            }
        
        # 总结
        self.print_summary()
        
        # 保存结果
        self.save_results()
        
        return self.results['mode'] == 'online'
    
    def print_summary(self):
        """打印总结"""
        self.print_header("测试总结")
        
        mode_desc = {
            'online': '✅ 在线模式 (数据库已连接)',
            'offline': '⚠️  离线模式 (模块可用，数据库未连接)'
        }
        
        print(f"  模式: {mode_desc.get(self.results['mode'], '未知')}\n")
        
        print("  测试结果:")
        for phase, result in self.results['phases'].items():
            status = result.get('status', 'unknown')
            if status == 'success':
                icon = '✅'
            elif status == 'skipped':
                icon = '⊘'
            elif status == 'unavailable':
                icon = '⚠️'
            else:
                icon = '❌'
            
            time_ms = result.get('time_ms', 0)
            time_str = f" ({time_ms}ms)" if time_ms > 0 else ""
            print(f"    {icon} {phase}{time_str}")
        
        print(f"\n  总耗时: {sum(self.results['timings'].values())}ms")
        
        if self.results['mode'] == 'offline':
            print("\n  ℹ️  离线测试完成。要运行完整测试:")
            print("    1. 启动 PostgreSQL 服务")
            print("    2. 启动 Neo4j 服务")
            print("    3. 重新运行此脚本")
    
    def save_results(self):
        """保存测试结果"""
        try:
            output_file = "storage_test_results.json"
            self.results['success'] = self.results['mode'] == 'online'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            self.log_success(f"结果已保存: {output_file}")
        except Exception as e:
            self.log_error(f"保存结果失败: {e}")
    
    def cleanup(self):
        """清理资源"""
        try:
            if self.storage and self.results['mode'] == 'online':
                self.storage.close()
                self.log_success("存储连接已关闭")
        except Exception as e:
            self.log_error(f"清理失败: {e}")


def main():
    """主函数"""
    tester = StorageFullTest()
    try:
        success = tester.run()
        return 0 if success else 1
    finally:
        tester.cleanup()


if __name__ == '__main__':
    sys.exit(main())
