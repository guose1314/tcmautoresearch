# tcmautoresearch Helm Chart

状态口径说明（2026-04-14）：

- Helm hook、Kubernetes Job、`kubectl exec` 迁移、Deployment ready 与探针通过，统一只表示部署或迁移动作完成，不自动等同于结构化存储处于“双写完成”。
- Helm / K8s 运维统一沿用 README 的结构化存储状态词汇表：双写完成、仅 PG 模式、待回填、schema drift 待治理。
- Neo4j 未启用、初始化失败或当前不可用时，集群内环境仍可能处于“仅 PG 模式”；历史图投影、Observe 版本元数据与文献学结构化资产也可能继续处于“待回填”。

## 安装

```bash
helm upgrade --install tcmautoresearch ./deploy/helm/tcmautoresearch -n tcm --create-namespace
```

## 使用已有 Secret

```bash
helm upgrade --install tcmautoresearch ./deploy/helm/tcmautoresearch \
  -n tcm --create-namespace \
  --set secrets.create=false \
  --set secrets.existingSecret=tcmautoresearch-secrets
```

## 自定义镜像标签

```bash
helm upgrade --install tcmautoresearch ./deploy/helm/tcmautoresearch \
  -n tcm --create-namespace \
  --set image.tag=v3.0.0
```

## 默认应用入口

Chart 当前会在 Deployment 中显式渲染应用启动命令，而不是依赖镜像默认 CMD：

```bash
python -m src.api.main --config config.yml --environment production --host 0.0.0.0 --port 8000
```

如需覆盖，可通过 `values.yaml` 中的 `app.command` 和 `app.args` 调整。

## 集群内数据库迁移（Alembic）

统一约定：不要为了切库去改 `alembic.ini`。Helm 场景下也沿用仓库统一的两条 Alembic 路径。

如果希望在安装/升级时自动执行迁移，而不是手工 `kubectl exec`：

```bash
helm upgrade --install tcmautoresearch ./deploy/helm/tcmautoresearch \
  -n tcm --create-namespace \
  --set migrations.enabled=true
```

默认会渲染为 `pre-install,pre-upgrade` Helm hook Job，执行：

```bash
alembic -x environment=production upgrade head
```

如果你使用的是原生 Kubernetes 清单，而不是 Helm hook，可直接应用独立示例 Job：

```bash
kubectl apply -n tcm -f deploy/k8s/tcmautoresearch-migrate-job.example.yaml
```

```bash
# 推荐：按环境走配置中心
kubectl exec -n tcm deploy/tcmautoresearch \
  -- alembic -x environment=production upgrade head
```

```bash
# 定向：显式指定目标库，适合一次性排障或历史库补迁移
kubectl exec -n tcm deploy/tcmautoresearch \
  -- alembic -x url=postgresql://tcm:your_password@<postgres-service>:5432/tcmautoresearch upgrade head
```

说明：

- 日常运维优先使用 `-x environment=production`，前提是你提供的生产配置已经指向正确的 PostgreSQL 服务。
- 只有在需要定向某一台实例时，才使用 `-x url=...`；其中主机名应写集群内 PostgreSQL Service 名称，而不是 `localhost`。
- 当 `migrations.enabled=true` 时，推荐优先使用自动 Job/hook；上面的 `kubectl exec` 只保留给一次性排障或历史库补基线。
- 如果目标库是早期通过 ORM `create_all()` 初始化、还没有 `alembic_version`，先执行 `stamp 3e5089f32f9a`，再执行 `upgrade head`。

## 结构化存储状态判读

Helm / K8s 运维验收时，统一按以下口径记录结构化存储状态：

| 状态 | 验收含义 | 集群侧动作 |
| --- | --- | --- |
| 双写完成 | PostgreSQL 与 Neo4j 都处于 active，可对同一轮 structured persist 的 session / artifact / 图投影做一致读取。 | 记录为主链健康，并继续确认没有遗留待回填项。 |
| 仅 PG 模式 | PostgreSQL 写入成立，但 Neo4j 未启用、初始化失败或当前不可用。 | 视为显式降级态；不要把 hook 成功或 Pod ready 误判成完整双写成功。 |
| 待回填 | 历史图投影、Observe 版本元数据或文献学结构化资产仍需 writeback / backfill。 | 补齐后再把该环境标记为结构化资产完整。 |
| schema drift 待治理 | 迁移、health check 或 drift 诊断仍有未清理告警。 | 先清理 drift，再推进发布、扩容或回填验收。 |
