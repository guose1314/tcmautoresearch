# tcmautoresearch Helm Chart

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
