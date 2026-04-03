# Docker 容器化部署说明

本文档对齐 Architecture 3.0 的平台化目标，提供可直接运行的容器化方案。

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

### 2.4 验证探针

```bash
curl http://127.0.0.1:8000/liveness
curl http://127.0.0.1:8000/readiness
```

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
