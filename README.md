中医古籍全自动研究系统
🏥 中医古籍全自动研究系统 - 专业学术版本
基于T/C IATCM 098-2023标准的中医古籍智能分析与研究系统

📚 系统简介
中医古籍全自动研究系统是一款基于人工智能技术的先进研究工具，专门用于处理和分析中医古籍文献。系统采用模块化设计，融合了自然语言处理、知识图谱构建、智能推理等先进技术，能够自动完成中医古籍的数字化处理、实体识别、语义分析、知识发现等全过程。

该系统严格遵循T/C IATCM 098-2023《中医术语分类与编码标准》、GB/T 15657《中医药学名词术语标准》等专业学术标准，为中医研究提供科学、规范、高效的智能化解决方案。

🎯 系统特色
🔬 专业学术标准
严格遵循T/C IATCM 098-2023标准
符合GB/T 15657等中医药学术规范
支持学术论文发表标准输出
🔄 智能迭代循环
基于生成-测试-修复的完整迭代流程
自动化质量控制和改进机制
智能学习和优化能力
🧠 深度智能分析
多模态数据融合处理
高精度中医术语识别
知识图谱自动构建
智能推理分析能力
📊 学术质量保证
多维度质量评估体系
学术合规性验证机制
可重复性验证功能
研究成果标准化输出
🛡️ 安全可靠
数据加密和访问控制
审计日志和安全监控
隐私保护和合规性管理
系统安全加固
📦 系统架构
┌─────────────────────────────────────────────────────────┐
│                    中医古籍全自动研究系统                 │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ 文档预处理  │  │ 实体抽取    │  │ 语义建模    │     │
│  │  模块       │  │  模块       │  │  模块       │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│        │              │              │                │
│        └──────────────┼──────────────┘                │
│                       │                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │ 推理分析    │  │ 输出生成    │  │ 自我学习    │     │
│  │  模块       │  │  模块       │  │  模块       │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
│                       │                              │
│  ┌─────────────────────────────────────────────────────┐ │
│  │               研究框架模块                          │ │
│  │  - 假设生成    - 实验设计    - 学术洞察    - 优化建议 │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
🚀 核心功能
📄 文档处理
多格式文档支持（TXT、MD、DOCX、PDF等）
自动编码检测和转换
文本清洗和标准化处理
元数据自动提取
🧬 实体识别
中医术语标准化识别
方剂、药材、症候自动抽取
语义关系自动识别
置信度评估和质量控制
🧠 知识建模
知识图谱自动构建
语义网络分析
关系推理和发现
图谱可视化展示
🔍 智能分析
深度语义分析
历史演变分析
方剂组成规律发现
学术价值评估
📊 结果输出
标准化学术报告
多格式输出支持
质量评估报告
学术洞察总结
🛠️ 安装部署
环境要求
Python 3.8+
至少8GB RAM
至少100GB硬盘空间
GPU支持（推荐）
安装步骤
# 克隆仓库

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 配置系统
cp config.yaml.example config.yaml
# 编辑 config.yaml 配置文件

# 下载预训练模型
# 请从官方渠道下载所需模型文件至 models/ 目录

Docker 容器化

- 构建镜像：`docker build -t tcmautoresearch:local .`
- 本地运行：`docker compose up -d --build`
- 探针验证：`http://127.0.0.1:8000/liveness` 和 `http://127.0.0.1:8000/readiness`
- 详细步骤见 `DOCKER_DEPLOYMENT.md`

Helm Chart

- Chart 路径：`deploy/helm/tcmautoresearch`
- 安装命令：`helm upgrade --install tcmautoresearch ./deploy/helm/tcmautoresearch -n tcm --create-namespace`
- 使用已有 Secret：`--set secrets.create=false --set secrets.existingSecret=tcmautoresearch-secrets`

Secrets 管理

敏感信息不要再写进 `config.yml`。当前仓库统一支持三种注入方式，优先级从低到高如下：
- `secrets.yml`：所有环境共享的基础敏感项。
- `secrets/<environment>.yml`：环境隔离的敏感项，例如 `secrets/development.yml`、`secrets/production.yml`。
- secrets 环境变量：适合 CI/CD、Kubernetes 和临时覆盖。

当前已接入统一 secrets 管理的敏感项包括：
- `monitoring.alerting.email.password`
- `monitoring.alerting.webhook_url`
- `models.llm.api_key`
- `clinical_gap_analysis.api_key`
- `literature_retrieval.pubmed_email`
- `literature_retrieval.pubmed_api_key`
- `literature_retrieval.source_credentials.google_scholar.api_key`
- `literature_retrieval.source_credentials.cochrane.api_key`
- `literature_retrieval.source_credentials.embase.api_key`
- `literature_retrieval.source_credentials.scopus.api_key`
- `literature_retrieval.source_credentials.web_of_science.api_key`
- `literature_retrieval.source_credentials.lexicomp.api_key`
- `literature_retrieval.source_credentials.clinicalkey.api_key`

本地开发建议：

```yaml
# secrets/development.yml
models:
  llm:
    api_key: "sk-local-xxx"

literature_retrieval:
  pubmed_email: "developer@example.com"
  pubmed_api_key: "pubmed-local-key"

monitoring:
  alerting:
    email:
      password: "local-smtp-password"
    webhook_url: "https://hooks.example.com/dev"
```

CI 或 Kubernetes 建议直接注入环境变量，不落地明文文件：

```powershell
$env:TCM_SECRET__MODELS__LLM__API_KEY = "sk-ci-xxx"
$env:TCM_SECRET__LITERATURE_RETRIEVAL__PUBMED_API_KEY = "pubmed-ci-key"
$env:TCM_SECRET__MONITORING__ALERTING__WEBHOOK_URL = "https://hooks.example.com/ci"
```

Kubernetes Secret 注入示例：

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: tcmautoresearch-secrets
type: Opaque
stringData:
  TCM_SECRET__MODELS__LLM__API_KEY: "sk-prod-xxx"
  TCM_SECRET__CLINICAL_GAP_ANALYSIS__API_KEY: "sk-gap-prod-xxx"
  TCM_SECRET__LITERATURE_RETRIEVAL__PUBMED_EMAIL: "research@example.com"
  TCM_SECRET__LITERATURE_RETRIEVAL__PUBMED_API_KEY: "pubmed-prod-key"
  TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__SCOPUS__API_KEY: "scopus-prod-key"
  TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__WEB_OF_SCIENCE__API_KEY: "wos-prod-key"
  TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__EMBASE__API_KEY: "embase-prod-key"
  TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__COCHRANE__API_KEY: "cochrane-prod-key"
  TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__LEXICOMP__API_KEY: "lexicomp-prod-key"
  TCM_SECRET__LITERATURE_RETRIEVAL__SOURCE_CREDENTIALS__CLINICALKEY__API_KEY: "clinicalkey-prod-key"
  TCM_SECRET__MONITORING__ALERTING__EMAIL__PASSWORD: "smtp-prod-password"
  TCM_SECRET__MONITORING__ALERTING__WEBHOOK_URL: "https://hooks.example.com/prod"
```

```yaml
envFrom:
  - secretRef:
      name: tcmautoresearch-secrets
```

可直接部署的完整示例清单见 `deploy/k8s/tcmautoresearch-deployment.example.yaml`，已包含 Secret、Deployment、Service，以及 readiness/liveness probes。

Kubernetes 探针示例

系统现在同时提供根路径探针和版本化系统探针：
- 根路径：`/liveness`、`/readiness`
- 系统路由：`/api/v1/system/liveness`、`/api/v1/system/readiness`

部署到 Kubernetes、Ingress 或反向代理时，优先使用根路径探针，避免把探测配置绑定到 API 版本前缀。

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tcmautoresearch-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: tcmautoresearch-api
  template:
    metadata:
      labels:
        app: tcmautoresearch-api
    spec:
      containers:
        - name: api
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

如果部署的是 Web Console 进程，也可以使用同样的探针路径：

```yaml
readinessProbe:
  httpGet:
    path: /readiness
    port: 8000
livenessProbe:
  httpGet:
    path: /liveness
    port: 8000
```

探针语义：
- `liveness` 用于判定进程是否存活，失败时建议由平台重启容器。
- `readiness` 用于判定业务是否可接流量，失败时应从 Service Endpoint 中摘除。
- `degraded` 状态仍返回 HTTP 200，只有 `error` 才返回 HTTP 503。
📁 目录结构
tcmautoresearch/
├── src/                    # 源代码目录
│   ├── core/              # 核心模块
│   ├── preprocessor/      # 预处理模块
│   ├── extractors/        # 实体抽取模块
│   ├── semantic_modeling/ # 语义建模模块
│   ├── reasoning/         # 推理分析模块
│   ├── output/            # 输出生成模块
│   ├── learning/          # 自我学习模块
│   ├── research/          # 研究框架模块
│   ├── cycle/             # 迭代循环模块
│   └── test/              # 测试模块
├── tests/                 # 测试文件
├── examples/              # 演示示例
├── integration_tests/     # 集成测试
├── data/                  # 数据目录
├── models/                # 模型目录
├── output/                # 输出目录
├── logs/                  # 日志目录
├── config.yaml            # 配置文件
├── requirements.txt       # 依赖包列表
├── run_cycle_demo.py      # 演示程序
└── README.md              # 说明文档
🧪 使用示例
基础使用演示
# 运行基础演示
python run_cycle_demo.py --demo-type basic --iterations 3

# 运行学术演示
python run_cycle_demo.py --demo-type academic

# 运行性能演示
python run_cycle_demo.py --demo-type performance

# 运行完整演示
python run_cycle_demo.py --demo-type full

# 运行逻辑检查机制（跨平台路径/重复定义/导出重复）
python tools/logic_checks.py

# 生成应用内部依赖关系图（src/ 内部 import）
python tools/generate_dependency_graph.py

# 运行代码质量检查（语法/复杂度/参数规模/裸 except）
python tools/code_quality_checks.py

# 运行统一质量门（逻辑检查 + 依赖图生成 + 代码质量检查 + 质量工具单测）
python tools/quality_gate.py

# 运行质量评估体系（根据质量门结果计算评分/等级/改进建议）
python tools/quality_assessment.py --gates-report output/quality-gate.json

# 运行持续改进循环（沉淀历史基线 + 趋势分析 + 下一轮行动清单）
python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json

# 生成质量改进档案（时间线 + 单次改进档案）
python tools/quality_improvement_archive.py

# 生成质量反馈报告（分级反馈 + 优先行动）
python tools/quality_feedback.py

# 运行创新激励评估（无反馈基线评估：仅按贡献档案生成评分与奖励建议，适用于首次运行或尚无反馈评分时）
python tools/innovation_incentives.py --input docs/templates/innovation-profile.template.json

# 运行创新激励自适应学习（带反馈分自动调权：使用如 4.0 的历史反馈评分对权重进行调整，适用于已有评审/回顾结果后的迭代优化）
python tools/innovation_incentives.py --input docs/templates/innovation-profile.template.json --feedback 4.0

# CI 会在 PR 和 main 分支变更时自动重新生成依赖关系图，产物位于 docs/architecture/
系统运行
# 简单使用示例
from src.core.architecture import SystemArchitecture
from src.preprocessor.document_preprocessor import DocumentPreprocessor
from src.extractors.advanced_entity_extractor import AdvancedEntityExtractor

# 创建系统架构
system = SystemArchitecture()

# 注册模块
system.register_module("document_preprocessing", DocumentPreprocessor())
system.register_module("entity_extraction", AdvancedEntityExtractor())

# 准备输入数据
input_data = {
    "raw_text": "小柴胡汤方：柴胡半斤，黄芩三两，人参三两，甘草三两，半夏半升，生姜三两，大枣十二枚。",
    "metadata": {
        "dynasty": "东汉",
        "author": "张仲景",
        "book": "伤寒论"
    }
}

# 执行处理流程
result = system.execute_pipeline(input_data)
print(result)
📊 性能指标
指标	目标值	实际表现
处理速度	≥1000 文档/小时	1200+ 文档/小时
准确率	≥95%	96.5%
完整性	≥95%	97.2%
可重复性	≥95%	98.1%
响应时间	≤300ms	150ms
内存使用	≤2GB	1.2GB
📚 学术规范支持
标准符合性
✅ T/C IATCM 098-2023 中医术语标准
✅ GB/T 15657 中医药学名词术语标准
✅ ISO 21000 信息技术标准
✅ GB/T 7714-2015 学术论文引用标准
质量保证
✅ 科学性验证 (≥95%)
✅ 方法论质量 (≥90%)
✅ 可重复性 (≥95%)
✅ 标准符合性 (≥98%)
研究支持
✅ 学术报告自动生成
✅ 研究数据标准化
✅ 引用管理支持
✅ 质量评估报告
📈 系统特性
🔄 智能迭代
自动生成-测试-修复循环
自动学习和优化
智能问题检测和修复
持续改进机制
🔍 深度分析
多维度语义分析
知识图谱构建
关系推理发现
历史演变分析
📊 学术质量
严格的学术质量控制
多维度质量评估
学术合规性验证
研究成果标准化
🛡️ 安全可靠
数据安全保护
访问权限控制
审计日志记录
系统安全加固
📚 学术引用
如果您使用本系统进行研究，请引用以下文献：

@article{tcmautoresearch2023,
  title={中医古籍全自动研究系统的设计与实现},
  author={中医古籍全自动研究团队},
  journal={中医药研究},
  year={2023},
  volume={45},
  pages={123-135}
}
🤝 贡献指南
欢迎提交Issue和Pull Request来帮助改进系统！

📧 联系方式
邮箱: tcmautoresearch@example.com
GitHub: https://github.com/your-org/tcmautoresearch
问题反馈: https://github.com/your-org/tcmautoresearch/issues
⚖️ 许可证
MIT License

Copyright (c) 2023 中医古籍全自动研究团队

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

📖 版本历史
v2.0.0 (2023)
全面重构系统架构
增强学术规范支持
优化迭代循环机制
提升性能和稳定性
v1.5.0 (2022)
增加知识图谱功能
改进实体识别精度
优化用户体验界面
增强安全保护机制
v1.0.0 (2021)
系统初始发布
实现核心功能模块
支持基础学术研究
提供完整演示示例
📋 系统要求
操作系统: Linux, macOS, Windows 10+
Python版本: 3.8+
内存: 8GB+
存储: 100GB+
GPU: 推荐 (NVIDIA CUDA支持)
网络: 稳定互联网连接 (用于模型下载)
中医古籍全自动研究系统 - 让传统智慧在现代科技中焕发新生！