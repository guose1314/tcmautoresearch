#!/usr/bin/env python3
"""
中医古籍研究系统 - 存储系统全流程测试
小样本性能和可用性验证
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class StorageSystemTester:
    """存储系统测试器"""
    
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'phases': {},
            'statistics': {
                'total_time_ms': 0,
                'entities_count': 0,
                'relationships_count': 0,
                'success': False,
            }
        }
        self.storage = None
        self.doc_id = None
        self.entity_ids = []
        self.timings = {}
    
    def print_header(self, title: str):
        """打印标题"""
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}\n")
    
    def print_step(self, step: str, status: str):
        """打印步骤状态"""
        icon = "✅" if status == "success" else "⏱️" if status == "running" else "❌"
        print(f"{icon} {step}")
    
    def test_imports(self) -> bool:
        """测试1: 验证导入"""
        self.print_header("测试1: 模块导入")
        
        try:
            from src.storage import UnifiedStorageDriver
            self.print_step("src.storage.UnifiedStorageDriver", "success")
            
            from src.storage import (
                Document,
                Entity,
                EntityRelationship,
                ProcessingStatistics,
                RelationshipType,
            )
            self.print_step("ORM模型导入", "success")
            
            logger.info("✅ 所有模块导入成功")
            self.results['phases']['imports'] = {'status': 'success'}
            return True
        
        except Exception as e:
            logger.error(f"❌ 导入失败: {e}")
            self.results['phases']['imports'] = {'status': 'failed', 'error': str(e)}
            return False
    
    def test_database_connection(self) -> bool:
        """测试2: 数据库连接"""
        self.print_header("测试2: 数据库连接")
        
        start = time.time()
        
        try:
            from src.storage import UnifiedStorageDriver
            
            # 读取环境变量（如果设置）
            db_password = os.getenv('DB_PASSWORD', 'password')
            neo4j_password = os.getenv('NEO4J_PASSWORD', 'neo4j')
            
            pg_url = f"postgresql://tcm_user:{db_password}@localhost:5432/tcm_autoresearch"
            neo4j_uri = "neo4j://localhost:7687"
            neo4j_auth = ("neo4j", neo4j_password)
            
            logger.info(f"连接到 PostgreSQL: {pg_url}")
            logger.info(f"连接到 Neo4j: {neo4j_uri}")
            
            self.storage = UnifiedStorageDriver(pg_url, neo4j_uri, neo4j_auth)
            self.storage.initialize()
            
            self.print_step("PostgreSQL 连接", "success")
            self.print_step("Neo4j 连接", "success")
            
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"✅ 数据库连接成功 ({elapsed}ms)")
            
            self.results['phases']['connection'] = {
                'status': 'success',
                'time_ms': elapsed
            }
            self.timings['connection'] = elapsed
            return True
        
        except Exception as e:
            logger.error(f"❌ 连接失败: {e}")
            self.results['phases']['connection'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    def test_document_creation(self) -> bool:
        """测试3: 创建文档记录"""
        self.print_header("测试3: 创建文档记录")
        
        start = time.time()
        
        try:
            self.doc_id = self.storage.save_document(
                source_file="test_document_" + str(uuid4())[:8],
                objective="test_storage_cycle",
                raw_text_size=12345
            )
            
            self.print_step(f"保存文档: {self.doc_id}", "success")
            
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"✅ 文档创建成功 ({elapsed}ms)")
            
            self.results['phases']['document_creation'] = {
                'status': 'success',
                'doc_id': str(self.doc_id),
                'time_ms': elapsed
            }
            self.timings['document_creation'] = elapsed
            return True
        
        except Exception as e:
            logger.error(f"❌ 文档创建失败: {e}")
            self.results['phases']['document_creation'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    def create_test_entities(self) -> List[Dict[str, Any]]:
        """生成测试实体"""
        return [
            # 方剂
            {
                'name': '小柴胡汤',
                'type': 'formula',
                'confidence': 0.95,
                'position': 0,
                'length': 4,
                'alternative_names': ['和解方', '柴胡剂'],
                'description': '少阳和解方'
            },
            {
                'name': '四物汤',
                'type': 'formula',
                'confidence': 0.92,
                'position': 10,
                'length': 4,
                'description': '补血方'
            },
            # 中药
            {
                'name': '柴胡',
                'type': 'herb',
                'confidence': 0.98,
                'position': 5,
                'length': 2,
                'alternative_names': ['柴草', '柴胡根'],
                'metadata': {'nature': '苦微温', 'meridian': '归肝胆经'}
            },
            {
                'name': '黄芩',
                'type': 'herb',
                'confidence': 0.95,
                'position': 8,
                'length': 2,
                'metadata': {'nature': '苦寒', 'meridian': '归肺大肠经'}
            },
            {
                'name': '人参',
                'type': 'herb',
                'confidence': 0.94,
                'position': 12,
                'length': 2,
                'metadata': {'nature': '甘温', 'meridian': '归脾肺经'}
            },
            {
                'name': '当归',
                'type': 'herb',
                'confidence': 0.93,
                'position': 15,
                'length': 2,
                'metadata': {'nature': '甘辛温', 'meridian': '归心脾肝经'}
            },
            # 症候
            {
                'name': '少阳症',
                'type': 'syndrome',
                'confidence': 0.90,
                'position': 20,
                'length': 3,
                'description': '寒热往来，胸胁苦满'
            },
            {
                'name': '血虚',
                'type': 'syndrome',
                'confidence': 0.88,
                'position': 25,
                'length': 2,
                'description': '血液不足，营养缺乏'
            },
            # 功效
            {
                'name': '疏肝解郁',
                'type': 'efficacy',
                'confidence': 0.92,
                'position': 30,
                'length': 4,
                'description': '疏散肝气，解除郁结'
            },
            {
                'name': '补气健脾',
                'type': 'efficacy',
                'confidence': 0.91,
                'position': 35,
                'length': 4,
                'description': '补益气血，增强脾胃功能'
            },
        ]
    
    def test_entity_creation(self) -> bool:
        """测试4: 创建实体"""
        self.print_header("测试4: 创建实体 (10个)")
        
        start = time.time()
        
        try:
            entities = self.create_test_entities()
            
            self.entity_ids = self.storage.save_entities(self.doc_id, entities)
            
            self.print_step(f"保存实体: {len(self.entity_ids)} 个", "success")
            
            # 按类型统计
            type_count = {}
            for e in entities:
                t = e['type']
                type_count[t] = type_count.get(t, 0) + 1
            
            for etype, count in sorted(type_count.items()):
                logger.info(f"  - {etype}: {count}个")
            
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"✅ 实体创建成功 ({elapsed}ms, {elapsed/len(entities):.1f}ms/个)")
            
            self.results['phases']['entity_creation'] = {
                'status': 'success',
                'count': len(self.entity_ids),
                'count_by_type': type_count,
                'time_ms': elapsed,
                'time_per_entity_ms': round(elapsed / len(self.entity_ids), 2)
            }
            self.timings['entity_creation'] = elapsed
            self.results['statistics']['entities_count'] = len(self.entity_ids)
            return True
        
        except Exception as e:
            logger.error(f"❌ 实体创建失败: {e}")
            self.results['phases']['entity_creation'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    def create_test_relationships(self) -> List[Dict[str, Any]]:
        """生成测试关系"""
        # 假设entity_ids顺序为: 小柴胡汤(0), 四物汤(1), 柴胡(2), 黄芩(3), 人参(4), 当归(5), 少阳症(6), 血虚(7), 疏肝解郁(8), 补气健脾(9)
        return [
            # 方剂-中药 (君臣佐使)
            {'source_entity_id': self.entity_ids[0], 'target_entity_id': self.entity_ids[2], 'relationship_type': 'SOVEREIGN', 'confidence': 0.95, 'created_by_module': 'test'},
            {'source_entity_id': self.entity_ids[0], 'target_entity_id': self.entity_ids[3], 'relationship_type': 'MINISTER', 'confidence': 0.92, 'created_by_module': 'test'},
            {'source_entity_id': self.entity_ids[0], 'target_entity_id': self.entity_ids[4], 'relationship_type': 'MINISTER', 'confidence': 0.90, 'created_by_module': 'test'},
            
            {'source_entity_id': self.entity_ids[1], 'target_entity_id': self.entity_ids[5], 'relationship_type': 'SOVEREIGN', 'confidence': 0.93, 'created_by_module': 'test'},
            
            # 中药-功效
            {'source_entity_id': self.entity_ids[2], 'target_entity_id': self.entity_ids[8], 'relationship_type': 'HAS_EFFICACY', 'confidence': 0.91, 'created_by_module': 'test'},
            {'source_entity_id': self.entity_ids[4], 'target_entity_id': self.entity_ids[9], 'relationship_type': 'HAS_EFFICACY', 'confidence': 0.88, 'created_by_module': 'test'},
            {'source_entity_id': self.entity_ids[5], 'target_entity_id': self.entity_ids[9], 'relationship_type': 'HAS_EFFICACY', 'confidence': 0.90, 'created_by_module': 'test'},
            
            # 方剂-症候 (治疗)
            {'source_entity_id': self.entity_ids[0], 'target_entity_id': self.entity_ids[6], 'relationship_type': 'TREATS', 'confidence': 0.85, 'created_by_module': 'test'},
            {'source_entity_id': self.entity_ids[1], 'target_entity_id': self.entity_ids[7], 'relationship_type': 'TREATS', 'confidence': 0.82, 'created_by_module': 'test'},
        ]
    
    def test_relationship_creation(self) -> bool:
        """测试5: 创建关系"""
        self.print_header("测试5: 创建关系")
        
        start = time.time()
        
        try:
            relationships = self.create_test_relationships()
            
            rel_ids = self.storage.save_relationships(self.doc_id, relationships)
            
            self.print_step(f"保存关系: {len(rel_ids)} 个", "success")
            
            # 按关系类型统计
            type_count = {}
            for r in relationships:
                t = r['relationship_type']
                type_count[t] = type_count.get(t, 0) + 1
            
            for reltype, count in sorted(type_count.items()):
                logger.info(f"  - {reltype}: {count}个")
            
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"✅ 关系创建成功 ({elapsed}ms, {elapsed/len(relationships):.1f}ms/个)")
            
            self.results['phases']['relationship_creation'] = {
                'status': 'success',
                'count': len(rel_ids),
                'count_by_type': type_count,
                'time_ms': elapsed,
                'time_per_relationship_ms': round(elapsed / len(relationships), 2)
            }
            self.timings['relationship_creation'] = elapsed
            self.results['statistics']['relationships_count'] = len(rel_ids)
            return True
        
        except Exception as e:
            logger.error(f"❌ 关系创建失败: {e}")
            self.results['phases']['relationship_creation'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    def test_statistics_storage(self) -> bool:
        """测试6: 保存统计信息"""
        self.print_header("测试6: 保存统计信息")
        
        start = time.time()
        
        try:
            stats = {
                'formulas_count': 2,
                'herbs_count': 4,
                'syndromes_count': 2,
                'efficacies_count': 2,
                'relationships_count': 9,
                'graph_nodes_count': 10,
                'graph_edges_count': 9,
                'graph_density': 0.18,  # 9 / (10*9/2)
                'connected_components': 1,
                'source_modules': ['test'],
                'processing_time_ms': int((time.time() - start) * 1000)
            }
            
            success = self.storage.save_statistics(self.doc_id, stats)
            
            if success:
                self.print_step("保存统计数据", "success")
                logger.info(f"  - 图密度: {stats['graph_density']:.2f}")
                logger.info(f"  - 连通分量: {stats['connected_components']}")
                
                elapsed = int((time.time() - start) * 1000)
                logger.info(f"✅ 统计信息保存成功 ({elapsed}ms)")
                
                self.results['phases']['statistics_storage'] = {
                    'status': 'success',
                    'data': stats,
                    'time_ms': elapsed
                }
                self.timings['statistics_storage'] = elapsed
                return True
            else:
                raise Exception("保存返回False")
        
        except Exception as e:
            logger.error(f"❌ 统计保存失败: {e}")
            self.results['phases']['statistics_storage'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    def test_quality_metrics(self) -> bool:
        """测试7: 保存质量指标"""
        self.print_header("测试7: 保存质量指标")
        
        start = time.time()
        
        try:
            quality = {
                'confidence_score': 0.92,
                'completeness': 0.88,
                'entity_precision': 0.95,
                'relationship_precision': 0.90,
                'graph_quality_score': 0.88,
                'evaluator': 'test_suite',
                'assessment_notes': '小样本测试通过'
            }
            
            success = self.storage.save_quality_metrics(self.doc_id, quality)
            
            if success:
                self.print_step("保存质量指标", "success")
                logger.info(f"  - 置信度: {quality['confidence_score']:.2f}")
                logger.info(f"  - 完整性: {quality['completeness']:.2f}")
                logger.info(f"  - 精准度: {quality['entity_precision']:.2f}")
                
                elapsed = int((time.time() - start) * 1000)
                logger.info(f"✅ 质量指标保存成功 ({elapsed}ms)")
                
                self.results['phases']['quality_metrics'] = {
                    'status': 'success',
                    'data': quality,
                    'time_ms': elapsed
                }
                self.timings['quality_metrics'] = elapsed
                return True
            else:
                raise Exception("保存返回False")
        
        except Exception as e:
            logger.error(f"❌ 质量指标保存失败: {e}")
            self.results['phases']['quality_metrics'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    def test_queries(self) -> bool:
        """测试8: 数据查询验证"""
        self.print_header("测试8: 数据查询验证")
        
        start = time.time()
        
        try:
            # 查询1: 获取所有实体
            entities = self.storage.get_entities(self.doc_id)
            self.print_step(f"查询实体: {len(entities)} 个", "success")
            logger.info(f"  实体类型: {set(e['type'] for e in entities)}")
            
            # 查询2: 获取所有关系
            relationships = self.storage.get_relationships(self.doc_id)
            self.print_step(f"查询关系: {len(relationships)} 个", "success")
            logger.info(f"  关系类型: {set(r['type'].relationship_type for r in relationships if r.get('type'))}")
            
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"✅ 数据查询成功 ({elapsed}ms)")
            
            self.results['phases']['queries'] = {
                'status': 'success',
                'entities_retrieved': len(entities),
                'relationships_retrieved': len(relationships),
                'time_ms': elapsed
            }
            self.timings['queries'] = elapsed
            return True
        
        except Exception as e:
            logger.error(f"❌ 查询失败: {e}")
            self.results['phases']['queries'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    def test_storage_statistics(self) -> bool:
        """测试9: 获取存储系统统计"""
        self.print_header("测试9: 存储系统统计")
        
        start = time.time()
        
        try:
            stats = self.storage.get_storage_statistics()
            
            logger.info("PostgreSQL 统计:")
            pg_stats = stats.get('postgresql', {})
            logger.info(f"  - 文档数: {pg_stats.get('documents', 0)}")
            logger.info(f"  - 实体数: {pg_stats.get('entities', 0)}")
            logger.info(f"  - 关系数: {pg_stats.get('relationships', 0)}")
            
            logger.info("Neo4j 统计:")
            neo4j_stats = stats.get('neo4j', {})
            logger.info(f"  - 总节点数: {neo4j_stats.get('total_nodes', 0)}")
            logger.info(f"  - 总关系数: {neo4j_stats.get('total_relationships', 0)}")
            
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"✅ 统计查询成功 ({elapsed}ms)")
            
            self.results['phases']['storage_statistics'] = {
                'status': 'success',
                'postgresql': pg_stats,
                'neo4j': neo4j_stats,
                'time_ms': elapsed
            }
            self.timings['storage_statistics'] = elapsed
            return True
        
        except Exception as e:
            logger.error(f"❌ 统计查询失败: {e}")
            self.results['phases']['storage_statistics'] = {
                'status': 'failed',
                'error': str(e)
            }
            return False
    
    def run_all_tests(self) -> bool:
        """运行所有测试"""
        self.print_header("中医古籍研究系统 - 存储系统全流程测试")
        
        start_total = time.time()
        
        # 执行测试序列
        tests = [
            ("模块导入", self.test_imports),
            ("数据库连接", self.test_database_connection),
            ("创建文档", self.test_document_creation),
            ("创建实体", self.test_entity_creation),
            ("创建关系", self.test_relationship_creation),
            ("保存统计", self.test_statistics_storage),
            ("保存质量", self.test_quality_metrics),
            ("数据查询", self.test_queries),
            ("系统统计", self.test_storage_statistics),
        ]
        
        all_passed = True
        for test_name, test_func in tests:
            try:
                if not test_func():
                    all_passed = False
            except Exception as e:
                logger.error(f"❌ {test_name} 异常: {e}")
                all_passed = False
        
        # 总结
        total_elapsed = int((time.time() - start_total) * 1000)
        self.results['statistics']['total_time_ms'] = total_elapsed
        self.results['statistics']['success'] = all_passed
        
        self.print_summary(total_elapsed, all_passed)
        
        return all_passed
    
    def print_summary(self, total_elapsed: int, all_passed: bool):
        """打印测试总结"""
        self.print_header("测试总结")
        
        status = "✅ 全部通过" if all_passed else "❌ 部分失败"
        logger.info(f"状态: {status}")
        logger.info(f"总耗时: {total_elapsed}ms ({total_elapsed/1000:.2f}秒)")
        
        logger.info("\n⏱️  各阶段耗时:")
        for phase, elapsed in sorted(self.timings.items(), key=lambda x: -x[1]):
            logger.info(f"  {phase:.<40} {elapsed:>6}ms")
        
        logger.info(f"\n📊 数据统计:")
        logger.info(f"  实体数: {self.results['statistics']['entities_count']}")
        logger.info(f"  关系数: {self.results['statistics']['relationships_count']}")
        
        if self.results['statistics']['entities_count'] > 0:
            time_per_entity = total_elapsed / self.results['statistics']['entities_count']
            logger.info(f"  平均每实体耗时: {time_per_entity:.2f}ms")
        
        logger.info(f"\n💾 数据库状态:")
        
        pg_stats = self.results['phases'].get('storage_statistics', {}).get('postgresql', {})
        neo4j_stats = self.results['phases'].get('storage_statistics', {}).get('neo4j', {})
        
        logger.info(f"  PostgreSQL 实体: {pg_stats.get('entities', '?')}")
        logger.info(f"  PostgreSQL 关系: {pg_stats.get('relationships', '?')}")
        logger.info(f"  Neo4j 节点: {neo4j_stats.get('total_nodes', '?')}")
        logger.info(f"  Neo4j 关系: {neo4j_stats.get('total_relationships', '?')}")
        
        # 生成性能评级
        if total_elapsed < 5000:
            performance = "🚀 优秀 (< 5秒)"
        elif total_elapsed < 10000:
            performance = "✅ 良好 (5-10秒)"
        elif total_elapsed < 20000:
            performance = "⚠️  一般 (10-20秒)"
        else:
            performance = "❌ 需优化 (> 20秒)"
        
        logger.info(f"\n🎯 性能评级: {performance}")
    
    def save_results(self, output_file: str = "test_results.json"):
        """保存测试结果到JSON"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            logger.info(f"\n📄 测试结果已保存: {output_file}")
            return True
        except Exception as e:
            logger.error(f"保存结果失败: {e}")
            return False
    
    def close(self):
        """关闭存储连接"""
        try:
            if self.storage:
                self.storage.close()
                logger.info("✅ 存储连接已关闭")
        except Exception as e:
            logger.error(f"关闭连接失败: {e}")


def main():
    """主函数"""
    tester = StorageSystemTester()
    
    try:
        # 运行全流程测试
        success = tester.run_all_tests()
        
        # 保存结果
        tester.save_results("storage_test_results.json")
        
        # 返回状态码
        return 0 if success else 1
    
    finally:
        tester.close()


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
