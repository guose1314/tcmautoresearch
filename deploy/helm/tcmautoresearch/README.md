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
