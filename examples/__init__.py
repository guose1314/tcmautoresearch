# examples/__init__.py
"""
中医古籍全自动研究系统 - 专业学术演示示例初始化文件
"""

import logging

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "基于T/C IATCM 098-2023标准的中医古籍研究系统演示示例"

# 导入主要演示类和函数
from .demo_usage import DemoUsage, ExampleConfig, ExampleResult

# 模块导出
__all__ = [
    'DemoUsage',
    'ExampleConfig',
    'ExampleResult'
]

# 演示配置
DEMO_CONFIG = {
    'demo_info': {
        'name': '中医古籍全自动研究系统演示',
        'version': '2.0.0',
        'standards': ['T/C IATCM 098-2023', 'GB/T 15657', 'ISO 21000'],
        'principles': [
            '系统性原则',
            '科学性原则', 
            '实用性原则',
            '创新性原则'
        ]
    },
    'demo_scenarios': {
        'basic_usage': {
            'name': '基础使用演示',
            'description': '展示系统基本功能和使用流程',
            'complexity': 'beginner',
            'duration': '5分钟'
        },
        'advanced_analysis': {
            'name': '高级分析演示',
            'description': '展示系统高级分析功能和学术研究能力',
            'complexity': 'advanced',
            'duration': '10分钟'
        },
        'academic_research': {
            'name': '学术研究演示',
            'description': '展示系统在学术研究中的应用',
            'complexity': 'expert',
            'duration': '15分钟'
        }
    },
    'example_data': {
        'sample_documents': [
            '小柴胡汤方剂分析',
            '四物汤组成研究',
            '伤寒论方剂统计',
            '黄帝内经术语分析'
        ],
        'test_datasets': [
            '经典方剂数据集',
            '历史文献数据集',
            '现代研究数据集'
        ]
    },
    'academic_requirements': {
        'scientific_validity': 0.95,
        'methodological_quality': 0.90,
        'reproducibility': 0.95,
        'standard_compliance': 0.98,
        'performance_threshold': 0.85
    }
}

# 演示环境配置
DEMO_ENVIRONMENTS = {
    'development': {
        'name': '开发演示环境',
        'description': '用于日常演示和教学',
        'resources': {
            'cpu': '4核',
            'memory': '8GB',
            'storage': '100GB',
            'network': '100Mbps'
        },
        'configuration': {
            'debug_mode': True,
            'logging_level': 'INFO',
            'demo_mode': True
        }
    },
    'academic': {
        'name': '学术演示环境',
        'description': '用于学术研究和论文发表演示',
        'resources': {
            'cpu': '8核',
            'memory': '16GB',
            'storage': '500GB',
            'network': '1Gbps'
        },
        'configuration': {
            'debug_mode': False,
            'logging_level': 'DEBUG',
            'demo_mode': False,
            'academic_mode': True
        }
    }
}

# 演示流程配置
DEMO_FLOW = {
    'basic_workflow': [
        '数据输入',
        '预处理',
        '实体识别',
        '语义建模',
        '推理分析',
        '结果输出'
    ],
    'academic_workflow': [
        '数据准备',
        '学术规范验证',
        '多维度分析',
        '质量控制',
        '学术报告生成',
        '结果验证'
    ],
    'advanced_workflow': [
        '数据预处理',
        '特征提取',
        '模型训练',
        '深度分析',
        '知识图谱构建',
        '学术价值评估'
    ]
}

# 初始化日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info("中医古籍演示示例模块已初始化")

# 版本兼容性声明
VERSION_COMPATIBILITY = {
    'python': '>=3.8',
    'numpy': '>=1.21.0',
    'pandas': '>=1.3.0',
    'torch': '>=1.9.0',
    'transformers': '>=4.20.0',
    'networkx': '>=2.6.0'
}

# 演示指标
DEMO_METRICS = {
    'demo_success_rate': 0.0,
    'demo_execution_time': 0.0,
    'academic_quality_score': 0.0,
    'performance_score': 0.0,
    'user_satisfaction': 0.0
}

# 演示状态
DEMO_STATUS = {
    'initialized': False,
    'running': False,
    'completed': False,
    'successful': False
}
