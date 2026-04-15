# 存储系统部署指南

状态口径说明（2026-04-14）：

- 部署、验收、回填和排障统一使用 README 中“结构化存储状态词汇表”的四个状态词：双写完成、仅 PG 模式、待回填、schema drift 待治理。
- 当前主科研链的主写路径以 `StorageBackendFactory.transaction()` + `TransactionCoordinator` 为准；“组件已连接”“服务已启动”“迁移已完成”不自动等同于“双写完成”。
- Neo4j 未启用、初始化失败或当前不可用时，系统允许进入“仅 PG 模式”；历史图投影和 Observe 结构化资产则可能继续处于“待回填”。

## 前置要求

### 1. PostgreSQL 安装

#### Windows 安装

##### 方式1：使用安装程序

- 下载 PostgreSQL 14+：[PostgreSQL Windows 下载页](https://www.postgresql.org/download/windows/)
- 运行安装程序，记住 root 密码
- 默认端口：5432

##### 方式2：使用 Choco（如果已安装）

```powershell
choco install postgresql14
```

##### 方式3：使用 Docker

```powershell
docker run --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=password postgres:14
```

#### PostgreSQL 初始化

```powershell
# 登录PostgreSQL
psql -U postgres

# 创建数据库
CREATE DATABASE tcm_autoresearch;

# 创建用户
CREATE USER tcm_user WITH PASSWORD 'your_password';

# 授予权限
GRANT ALL PRIVILEGES ON DATABASE tcm_autoresearch TO tcm_user;
ALTER DATABASE tcm_autoresearch OWNER TO tcm_user;

# 退出
\q
```

---

### 2. Neo4j 安装

#### Neo4j Windows 安装

##### 下载和安装 Neo4j

从你的 D 盘目录：`D:\neo4j-community-5.26.23-windows`

##### 启动 Neo4j

```powershell
# 进入Neo4j目录
cd D:\neo4j-community-5.26.23-windows\bin

# 启动服务
./neo4j.exe console

# 或作为后台服务
./neo4j.exe install-service
./neo4j.exe start
```

##### 访问 Neo4j Browser

- 地址：[http://localhost:7474](http://localhost:7474)
- 默认用户: neo4j
- 默认密码: neo4j（首次登录需更改）

#### 修改配置

编辑 `D:\neo4j-community-5.26.23-windows\conf\neo4j.conf`

```ini
# 监听地址
dbms.default_listen_address=0.0.0.0
dbms.default_advertised_address=localhost

# 连接器端口
dbms.connector.bolt.listen_address=0.0.0.0:7687
dbms.connector.http.listen_address=0.0.0.0:7474

# 内存设置
dbms.memory.heap.initial_size=1G
dbms.memory.heap.max_size=2G
```

---

## Python 环境配置

### 1. 安装依赖

```bash
# 在虚拟环境中
pip install psycopg2-binary>=2.9.0,<3.0
pip install sqlalchemy>=2.0,<3.0
pip install neo4j>=5.0,<6.0
```

### 2. 配置文件

更新 `config.yml`：

```yaml
# 数据库配置
databases:
  postgresql:
    enabled: true
    driver: postgresql
    host: localhost
    port: 5432
    database: tcm_autoresearch
    user: tcm_user
    password: ${DB_PASSWORD}  # 使用环境变量
    pool_size: 10
    max_overflow: 20
    
  neo4j:
    enabled: true
    uri: neo4j://localhost:7687
    user: neo4j
    password: ${NEO4J_PASSWORD}  # 使用环境变量
    database: neo4j
```

### 3. 设置环境变量

```powershell
# PowerShell
$env:DB_PASSWORD = "your_postgres_password"
$env:NEO4J_PASSWORD = "your_neo4j_password"

# 或添加到 .env 文件
# 然后使用 python-dotenv 加载
```

### 4. Kubernetes 探针示例

如果 PostgreSQL、Neo4j 之外还会把 FastAPI API 或 Web Console 进程一并部署到 Kubernetes，建议直接使用应用根路径探针：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
    name: tcmautoresearch-app
spec:
    replicas: 1
    selector:
        matchLabels:
            app: tcmautoresearch-app
    template:
        metadata:
            labels:
                app: tcmautoresearch-app
        spec:
            containers:
                - name: app
                    image: ghcr.io/guose1314/tcmautoresearch:latest
                    ports:
                        - containerPort: 8000
                    readinessProbe:
                        httpGet:
                            path: /readiness
                            port: 8000
                        initialDelaySeconds: 10
                        periodSeconds: 10
                        timeoutSeconds: 3
                        failureThreshold: 3
                    livenessProbe:
                        httpGet:
                            path: /liveness
                            port: 8000
                        initialDelaySeconds: 20
                        periodSeconds: 15
                        timeoutSeconds: 3
                        failureThreshold: 3
```

说明：

- 推荐优先使用根路径 `/liveness` 和 `/readiness`，不要把集群探针绑死到 `/api/v1/system/...`。
- `readiness` 失败表示应用暂时不应接流量。
- `liveness` 失败表示进程已不可恢复，适合交给 Kubernetes 重启。
- 当系统处于 `degraded` 时，探针仍返回 200；仅 `error` 时返回 503。

### 5. 应用 Secrets 注入

应用层敏感项建议统一走 secrets 管理，而不是写在 `config.yml`。推荐方式：

- 本地开发：使用 `secrets.yml` 或 `secrets/development.yml`
- 测试/生产：通过 CI 或 Kubernetes Secret 注入 `TCM_SECRET__...` 环境变量

Kubernetes 示例：

```yaml
apiVersion: v1
kind: Secret
metadata:
    name: tcmautoresearch-secrets
type: Opaque
stringData:
    TCM_SECRET__MODELS__LLM__API_KEY: "sk-prod-xxx"
    TCM_SECRET__LITERATURE_RETRIEVAL__PUBMED_API_KEY: "pubmed-prod-key"
    TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__SCOPUS__API_KEY: "scopus-prod-key"
    TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__WEB_OF_SCIENCE__API_KEY: "wos-prod-key"
    TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__EMBASE__API_KEY: "embase-prod-key"
    TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__COCHRANE__API_KEY: "cochrane-prod-key"
    TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__LEXICOMP__API_KEY: "lexicomp-prod-key"
    TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__CLINICALKEY__API_KEY: "clinicalkey-prod-key"
    TCM_SECRET__MONITORING__ALERTING__WEBHOOK_URL: "https://hooks.example.com/prod"
```

```yaml
spec:
    template:
        spec:
            containers:
                - name: app
                    envFrom:
                        - secretRef:
                                name: tcmautoresearch-secrets
```

完整可部署示例见 [deploy/k8s/tcmautoresearch-deployment.example.yaml](deploy/k8s/tcmautoresearch-deployment.example.yaml)。

---

## 系统初始化脚本

### 方式1：使用 Python API

创建初始化脚本 `initialize_storage.py`：

```python
#!/usr/bin/env python3
"""
存储系统初始化脚本
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage import UnifiedStorageDriver

def main():
    # 读取配置
    pg_connection = os.getenv(
        'DATABASE_URL',
        'postgresql://tcm_user:password@localhost:5432/tcm_autoresearch'
    )
    neo4j_uri = os.getenv('NEO4J_URI', 'neo4j://localhost:7687')
    neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
    neo4j_password = os.getenv('NEO4J_PASSWORD', 'neo4j')
    
    print("初始化存储系统...")
    print(f"PostgreSQL: {pg_connection}")
    print(f"Neo4j: {neo4j_uri}")
    
    try:
        # 初始化存储驱动
        storage = UnifiedStorageDriver(
            pg_connection,
            neo4j_uri,
            (neo4j_user, neo4j_password)
        )
        storage.initialize()
        
        # 获取统计信息
        stats = storage.get_storage_statistics()
        print("\n存储系统初始化成功！")
        print(f"统计信息: {stats}")
        
        storage.close()
        
    except Exception as e:
        print(f"初始化失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
```

运行初始化：

```bash
python initialize_storage.py
```

### 方式2：使用 Alembic（推荐）

```bash
# 推荐：按环境走配置中心，不要手工修改 alembic.ini 的 sqlalchemy.url
alembic -x environment=production upgrade head
```

```bash
# 定向：显式指定目标库，适合本地临时库或一次性运维
alembic -x url=postgresql://tcm_user:your_password@localhost:5432/tcm_autoresearch upgrade head
```

运维约定：

- 日常迁移优先使用 `-x environment=production`，由配置中心统一解析 `config.yml` + `config/production.yml`，并读取 `TCM_DB_PASSWORD`。
- 只有在需要明确打某一台临时库或手工排障时，才使用 `-x url=...`。
- 不再建议通过手工编辑 `alembic.ini` 来切换生产目标库，这种方式最容易误打错库。

如果是历史本地 PostgreSQL，且当初通过 ORM `create_all()` 建库、没有 `alembic_version`，先执行一次基线标记：

```bash
alembic -x url=postgresql://tcm_user:your_password@localhost:5432/tcm_autoresearch stamp 3e5089f32f9a
alembic -x url=postgresql://tcm_user:your_password@localhost:5432/tcm_autoresearch upgrade head
```

当前 `head` 已包含：

- legacy native enum -> varchar 契约迁移
- `entities.alternative_names` / `processing_statistics.source_modules` -> PostgreSQL `varchar[]` 契约迁移

仅在一次性初始化、且明确不需要 Alembic 版本治理时，才考虑直接使用 SQLAlchemy 建表：

```bash
# 非推荐，仅适用于实验性空库初始化
python -c "
from src.storage import DatabaseManager, Base
from sqlalchemy import create_engine

engine = create_engine('postgresql://tcm_user:password@localhost:5432/tcm_autoresearch')
Base.metadata.create_all(engine)
print('数据表已创建')
"
```

---

## 验证安装

### 1. PostgreSQL 验证

```powershell
# 连接测试
psql -U tcm_user -d tcm_autoresearch -c "SELECT version();"

# 检查表
psql -U tcm_user -d tcm_autoresearch -c "\dt"
```

### 2. Neo4j 验证

```python
from src.storage import Neo4jDriver

neo4j = Neo4jDriver(
    'neo4j://localhost:7687',
    ('neo4j', 'your_password')
)
neo4j.connect()
stats = neo4j.get_graph_statistics()
print(stats)
neo4j.close()
```

### 3. 结构化存储状态判读

部署验收时，统一按以下口径判断状态：

| 状态 | 验收含义 | 运维动作 |
| --- | --- | --- |
| 双写完成 | PostgreSQL 与 Neo4j 都处于 active，可对同一轮 structured persist 的 session / artifact / 图投影做一致读取。 | 记录为主链健康；继续关注是否仍有待回填项。 |
| 仅 PG 模式 | PostgreSQL 写入成立，但 Neo4j 未启用、初始化失败或不可用。 | 视为显式降级态，不能对外宣称完整双写成功。 |
| 待回填 | 历史图投影、Observe 版本元数据或文献学结构化资产仍需 writeback / backfill。 | 在发布前执行补齐，并把结果并入验收记录。 |
| schema drift 待治理 | 迁移、health check 或 drift 诊断仍有未清理告警。 | 先治理 schema / contract 偏差，再确认结构化状态收口。 |

---

## 集成到现有系统

### 1. 修改输出生成模块

在 `src/output/output_generator.py` 中添加存储集成：

```python
from src.storage import UnifiedStorageDriver
from uuid import UUID

class OutputGenerator(BaseModule):
    def __init__(self, config=None, storage_driver=None):
        super().__init__("output_generator", config)
        self.storage = storage_driver
    
    def _do_execute(self, context):
        # ... 现有逻辑 ...
        
        # 新增：保存到数据库
        if self.storage and 'document_id' in context:
            self.storage.save_entities(
                context['document_id'],
                context.get('entities', [])
            )
            self.storage.save_relationships(
                context['document_id'],
                context.get('relationships', [])
            )
        
        return output_data
```

### 2. 修改当前 cycle 运行时链路

旧的 cycle 主循环子系统已删除。当前应在 `run_cycle_demo.py`、`src/cycle/cycle_runner.py` 或 `src/cycle/cycle_research_session.py` 接入存储驱动，例如：

```python
from src.cycle.cycle_runner import execute_real_module_pipeline
from src.storage import UnifiedStorageDriver


def process_with_storage(source_file: str, raw_text: str, config: dict) -> list[dict]:
    storage = None
    if config.get("storage", {}).get("enabled", False):
        pg_url = config["storage"]["postgresql"]["url"]
        neo4j_uri = config["storage"]["neo4j"]["uri"]
        neo4j_auth = (
            config["storage"]["neo4j"]["user"],
            config["storage"]["neo4j"]["password"],
        )
        storage = UnifiedStorageDriver(pg_url, neo4j_uri, neo4j_auth)
        storage.initialize()

    try:
        if storage:
            document_id = storage.save_document(
                source_file=source_file,
                objective="automatic_analysis",
                raw_text_size=len(raw_text),
            )
        else:
            document_id = None

        module_results = execute_real_module_pipeline(
            {
                "source_file": source_file,
                "raw_text": raw_text,
                "document_id": document_id,
            }
        )
        final_context = module_results[-1]["input_data"] if module_results else {}

        if storage and document_id:
            storage.save_entities(document_id, final_context.get("entities", []))
            storage.save_relationships(
                document_id,
                final_context.get("relationships", final_context.get("semantic_relationships", [])),
            )
            storage.save_statistics(document_id, final_context.get("statistics", {}))

        return module_results
    finally:
        if storage:
            storage.close()
```

---

## 常见问题

### Q1: PostgreSQL 连接被拒绝

**问题**：`psycopg2.OperationalError: could not connect to server`

**解决方案**：

1. 检查PostgreSQL服务是否运行：`services.msc` → 搜索PostgreSQL
2. 检查端口：`netstat -ano | findstr :5432`
3. 检查防火墙规则
4. 验证连接字符串中的主机、端口、用户名、密码

### Q2: Neo4j 认证失败

**问题**：`neo4j.exceptions.AuthError: The client is unauthorized`

**解决方案**：

1. 确认Neo4j正在运行
2. 重置密码：访问 [http://localhost:7474](http://localhost:7474) → 重置
3. 检查URI格式（bolt vs http）
4. 防火墙是否开放7687端口

### Q3: 内存不足

**解决方案**：

- PostgreSQL：增加 `shared_buffers`, `effective_cache_size`
- Neo4j：增加 `dbms.memory.heap.max_size`

### Q4: UUID冲突

**解决方案**：

- 使用 `uuid-ossp` 扩展（自动处理）
- 或使用 `uuid.uuid4()` 生成唯一ID

---

## 备份和恢复

### PostgreSQL 备份

```bash
# 备份单个数据库
pg_dump -U tcm_user -d tcm_autoresearch > backup_20260328.sql

# 恢复
psql -U tcm_user -d tcm_autoresearch < backup_20260328.sql
```

### Neo4j 备份

```bash
# 使用Neo4j Admin
neo4j-admin database dump neo4j backup_20260328.dump
```

---

## 性能优化

### 1. PostgreSQL 索引

```sql
-- 已在 db_models.py 中定义，但可以手动添加更多
CREATE INDEX idx_entity_name_type ON entities(name, type);
CREATE INDEX idx_relationship_confidence ON entity_relationships(confidence DESC);
```

### 2. Neo4j 索引

```cypher
-- 创建索引
CREATE INDEX entity_id_idx FOR (n:Entity) ON (n.id);
CREATE INDEX formula_name_idx FOR (n:Formula) ON (n.name);
```

### 3. 连接池优化

在 `db_models.py` 中调整：

```python
engine = create_engine(
    connection_string,
    pool_size=20,           # 增加连接池大小
    max_overflow=40,        # 允许更多溢出连接
    pool_pre_ping=True,     # 检查连接有效性
    echo=False
)
```

---

## 监控和维护

### 定期任务

```bash
# 每周：数据库维护
VACUUM ANALYZE;

# 每月：检查日志
SELECT COUNT(*) FROM processing_logs WHERE timestamp > NOW() - INTERVAL '30 days';

# 定期清理旧数据（可选）
DELETE FROM processing_logs WHERE timestamp < NOW() - INTERVAL '90 days';
```

---

## 参考文档

- [PostgreSQL 文档](https://www.postgresql.org/docs/)
- [Neo4j 文档](https://neo4j.com/docs/)
- [SQLAlchemy 文档](https://docs.sqlalchemy.org/)
- [Neo4j Python 驱动文档](https://neo4j.com/docs/driver-manual/current/)
