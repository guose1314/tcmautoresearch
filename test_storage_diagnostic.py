#!/usr/bin/env python3
"""存储系统诊断测试 - 逐步检查各个模块"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

print("=" * 60)
print("存储系统诊断测试")
print("=" * 60)

# 测试1: 模块导入
print("\n[测试1] 模块导入...")
try:
    from src.storage import (
        Database,
        Document,
        Entity,
        EntityRelationship,
        UnifiedStorageDriver,
    )
    print("✅ 所有模块导入成功")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

# 测试2: 枚举类型
print("\n[测试2] 枚举类型...")
try:
    from src.storage.db_models import EntityTypeEnum, ProcessStatusEnum
    print(f"✅ EntityTypeEnum: {list(EntityTypeEnum)}")
    print(f"✅ ProcessStatusEnum: {list(ProcessStatusEnum)}")
except Exception as e:
    print(f"❌ 测试失败: {e}")

# 测试3: 环境变量和连接配置
print("\n[测试3] 连接配置...")
import os

db_password = os.getenv('DB_PASSWORD', 'password')
neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')

pg_url = f"postgresql://tcm_user:{db_password}@localhost:5432/tcm_autoresearch"
neo4j_uri = "neo4j://localhost:7687"
neo4j_auth = ("neo4j", neo4j_password)

print(f"PostgreSQL: {pg_url.replace(db_password, '***')}")
print(f"Neo4j: {neo4j_uri}")
print(f"Neo4j Auth: ('neo4j', '{neo4j_password}')")

# 测试4: 初始化存储驱动(可选)
print("\n[测试4] 存储驱动初始化...")
try:
    storage = UnifiedStorageDriver(pg_url, neo4j_uri, neo4j_auth)
    print("⏱️  正在连接数据库...")
    storage.initialize()
    print("✅ 存储驱动初始化成功")
    
    # 测试基本功能
    print("\n[测试5] 基本功能...")
    doc_id = storage.save_document("test_doc", "diagnostic_test", 1000)
    print(f"✅ 文档创建成功: {doc_id}")
    
    # 清理
    storage.close()
    print("✅ 连接已清理")
    
except ConnectionError as e:
    print(f"⚠️  数据库连接失败(预期): {e}")
    print("   这正常 - 数据库可能未运行")
except Exception as e:
    print(f"❌ 初始化失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)
