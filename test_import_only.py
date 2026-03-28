#!/usr/bin/env python3
"""极简导入测试"""

import sys

print("\\n===== 测试模块导入 =====\\n")

try:
    print("正在导入 src.storage.db_models...")
    from src.storage.db_models import Entity, EntityTypeEnum
    print("✅ db_models 导入成功")
except Exception as e:
    print(f"❌ db_models 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("\\n正在导入 src.storage.neo4j_driver...")
    from src.storage.neo4j_driver import Neo4jDriver
    print("✅ neo4j_driver 导入成功")
except Exception as e:
    print(f"❌ neo4j_driver 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("\\n正在导入 src.storage.storage_driver...")
    from src.storage.storage_driver import UnifiedStorageDriver
    print("✅ storage_driver 导入成功")
except Exception as e:
    print(f"❌ storage_driver 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\\n✅ 全部导入成功！\\n")
