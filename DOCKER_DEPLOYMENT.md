# Docker 容器化部署说明

本文档对齐 Architecture 3.0 的平台化目标，提供可直接运行的容器化方案。

状态口径说明（2026-04-14）：

- 容器部署、回填、排障统一使用 README 中“结构化存储状态词汇表”的四个状态词：双写完成、仅 PG 模式、待回填、schema drift 待治理。
- 当前主科研链的主写路径以 `StorageBackendFactory.transaction()` + `TransactionCoordinator` 为准；容器内“服务已启动”“探针通过”“迁移完成”不自动等同于“双写完成”。
- Neo4j 未启用、初始化失败或当前不可用时，容器化部署仍可能处于“仅 PG 模式”；历史图投影与 Observe 结构化资产则可能继续处于“待回填”。

## 1. 产物清单

- Dockerfile: 生产镜像构建文件
- .dockerignore: 构建上下文过滤
- docker-compose.yml: 本地一键启动
- deploy/k8s/tcmautoresearch-deployment.example.yaml: Kubernetes Secret + Deployment + Service 示例

## 2. 本地 Docker 运行

### 2.1 准备配置与 secrets

1. 准备配置文件
   - config.yml
   - config/development.yml

2. 准备 secrets 文件（示例见 secrets.example.yml）
   - secrets.yml
   - 或 secrets/development.yml

3. 可选：准备 .env（用于 compose 的 env_file）

### 2.2 构建镜像

```bash
docker build -t tcmautoresearch:local .
```

### 2.3 启动服务

```bash
docker compose up -d --build
```

说明：当前镜像和 compose 应用服务都会显式启动独立 REST API 入口：

```bash
python -m src.api.main --config config.yml --environment production --host 0.0.0.0 --port 8000
```

这样容器内的 `/health`、`/liveness`、`/readiness` 与本地 API 调试入口保持一致，不再依赖 legacy web 启动路径。

### 2.4 验证探针

```bash
curl http://127.0.0.1:8000/liveness
curl http://127.0.0.1:8000/readiness
```

### 2.5 容器内执行数据库迁移（Alembic）

统一约定：不要进入容器后手工修改 `alembic.ini` 的 `sqlalchemy.url`。容器运维也沿用主仓库的两条统一路径。

```bash
# 推荐：按环境走配置中心
docker compose exec tcmautoresearch \
   alembic -x environment=production upgrade head
```

```bash
# 定向：显式指定目标库，适合一次性排障或历史库处理
docker compose exec tcmautoresearch \
   alembic -x url=postgresql://tcm:your_password@postgres:5432/tcmautoresearch upgrade head
```

说明：

- `docker-compose.yml` 里的应用服务已经注入了 `TCM_ENV=production`、`TCM_DB_PASSWORD` 和 `TCM_NEO4J_PASSWORD`，所以常规场景优先使用 `-x environment=production`。
- 容器内如果显式写 PostgreSQL URL，主机名必须使用 Compose 服务名 `postgres`，不要写 `localhost`；在容器里 `localhost` 指向的是应用容器本身。
- 如果目标库是早期通过 ORM `create_all()` 初始化、还没有 `alembic_version`，先基线标记再升级：

```bash
docker compose exec tcmautoresearch \
   alembic -x url=postgresql://tcm:your_password@postgres:5432/tcmautoresearch stamp 3e5089f32f9a

docker compose exec tcmautoresearch \
   alembic -x url=postgresql://tcm:your_password@postgres:5432/tcmautoresearch upgrade head
```

- 当前 `head` 已包含 legacy enum -> varchar，以及字符串列表列 -> `varchar[]` 的 PostgreSQL 契约迁移。

### 2.6 结构化存储状态判读

容器化部署验收时，统一按以下口径记录结构化存储状态：

| 状态 | 验收含义 | 容器侧动作 |
| --- | --- | --- |
| 双写完成 | PostgreSQL 与 Neo4j 都处于 active，可对同一轮 structured persist 的 session / artifact / 图投影做一致读取。 | 记录为主链健康，并继续确认没有遗留待回填项。 |
| 仅 PG 模式 | PostgreSQL 写入成立，但 Neo4j 未启用、初始化失败或不可用。 | 视为显式降级态；不要把探针通过误判成完整双写成功。 |
| 待回填 | 历史图投影、Observe 版本元数据或文献学结构化资产仍需 writeback / backfill。 | 补齐后再把该环境标记为结构化资产完整。 |
| schema drift 待治理 | 迁移、health check 或 drift 诊断仍有未清理告警。 | 先清理 drift，再推进发布或回填验收。 |

## 3. CI 注入 secrets（推荐）

CI 中不落地 secrets 文件，直接注入环境变量：

```text
TCM_SECRET__MODELS__LLM__API_KEY
TCM_SECRET__CLINICAL_GAP_ANALYSIS__API_KEY
TCM_SECRET__LITERATURE_RETRIEVAL__PUBMED_EMAIL
TCM_SECRET__LITERATURE_RETRIEVAL__PUBMED_API_KEY
TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__SCOPUS__API_KEY
TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__WEB_OF_SCIENCE__API_KEY
TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__EMBASE__API_KEY
TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__COCHRANE__API_KEY
TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__LEXICOMP__API_KEY
TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__CLINICALKEY__API_KEY
TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__GOOGLE_SCHOLAR__API_KEY
TCM_SECRET__MONITORING__ALERTING__EMAIL__PASSWORD
TCM_SECRET__MONITORING__ALERTING__WEBHOOK_URL
```

## 4. Kubernetes 部署

直接使用示例清单：

```bash
kubectl apply -f deploy/k8s/tcmautoresearch-deployment.example.yaml
```

说明：

- readinessProbe: /readiness
- livenessProbe: /liveness
- 使用 envFrom 引入 Secret，符合统一 secrets 命名规范

## 5. Helm 安装

Chart 已提供：`deploy/helm/tcmautoresearch`

```bash
helm upgrade --install tcmautoresearch ./deploy/helm/tcmautoresearch -n tcm --create-namespace
```

使用已有 Secret（不在 Chart 中创建 Secret）：

```bash
helm upgrade --install tcmautoresearch ./deploy/helm/tcmautoresearch \
   -n tcm --create-namespace \
   --set secrets.create=false \
   --set secrets.existingSecret=tcmautoresearch-secrets
```

## 6. 常见问题

1. 镜像体积过大
   - requirements.txt 包含大量数据科学依赖，建议后续拆分 runtime requirements

2. OCR 相关报错
   - Dockerfile 已安装 tesseract-ocr；若需中文识别，可在基础镜像内追加语言包

3. 本地模型路径无效
   - 确保 ./models 挂载到容器 /app/models，且配置中的模型路径与其一致
