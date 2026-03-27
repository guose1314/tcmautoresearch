# tests/__init__.py
"""
中医古籍全自动研究系统 - 专业学术测试套件初始化文件
"""

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "基于T/C IATCM 098-2023标准的中医古籍研究系统测试套件"

# 注意：避免在包导入阶段触发重量级模块导入。
# 具体测试类请在调用方按需导入。

# 模块导出
# 按需导入策略下，不在包级别暴露具体测试类符号。
__all__: list[str] = []

# 测试配置
TEST_SUITE_CONFIG = {
    'test_suite_info': {
        'name': '中医古籍全自动研究系统测试套件',
        'version': '2.0.0',
        'standards': ['T/C IATCM 098-2023', 'GB/T 15657', 'ISO 21000'],
        'principles': [
            '系统性原则',
            '科学性原则', 
            '实用性原则',
            '创新性原则'
        ]
    },
    'test_categories': {
        'interface_consistency': {
            'name': '接口一致性测试',
            'description': '测试各模块接口的一致性和兼容性',
            'priority': 'high',
            'coverage_target': 0.95
        },
        'cycle_system': {
            'name': '循环系统测试',
            'description': '测试迭代循环系统的完整性和正确性',
            'priority': 'high',
            'coverage_target': 0.90
        },
        'full_cycle': {
            'name': '完整循环测试',
            'description': '测试整个系统的端到端功能',
            'priority': 'high',
            'coverage_target': 0.85
        }
    },
    'quality_metrics': {
        'test_coverage': 0.90,
        'test_pass_rate': 0.95,
        'test_execution_time': 600,  # 秒
        'failure_rate_threshold': 0.05,
        'performance_threshold': 0.85
    },
    'academic_requirements': {
        'scientific_validity': 0.95,
        'methodological_quality': 0.90,
        'reproducibility': 0.95,
        'standard_compliance': 0.98
    }
}

# 测试标准和规范
TEST_STANDARDS = {
    'academic_standards': {
        'T/C IATCM 098-2023': {
            'description': '中医术语分类与编码标准',
            'requirements': [
                '术语标准化',
                '分类体系一致性',
                '编码规范性',
                '质量控制要求'
            ]
        },
        'GB/T 15657': {
            'description': '中医药学名词术语标准',
            'requirements': [
                '术语权威性',
                '定义准确性',
                '使用规范性',
                '更新时效性'
            ]
        },
        'ISO 21000': {
            'description': '信息技术标准',
            'requirements': [
                '系统兼容性',
                '数据完整性',
                '性能稳定性',
                '安全可靠性'
            ]
        }
    },
    'quality_standards': {
        'test_quality': {
            'completeness': 0.95,
            'accuracy': 0.92,
            'consistency': 0.90,
            'reliability': 0.95
        },
        'academic_quality': {
            'scientific_validity': 0.95,
            'methodological_rigor': 0.90,
            'reproducibility': 0.95,
            'standard_compliance': 0.98
        }
    }
}

# 测试环境配置
TEST_ENVIRONMENTS = {
    'development': {
        'name': '开发环境',
        'description': '用于日常开发和单元测试',
        'resources': {
            'cpu': '4核',
            'memory': '8GB',
            'storage': '100GB',
            'network': '100Mbps'
        },
        'configuration': {
            'debug_mode': True,
            'logging_level': 'DEBUG',
            'test_coverage': True
        }
    },
    'staging': {
        'name': '预生产环境',
        'description': '用于集成测试和系统测试',
        'resources': {
            'cpu': '8核',
            'memory': '16GB',
            'storage': '500GB',
            'network': '1Gbps'
        },
        'configuration': {
            'debug_mode': False,
            'logging_level': 'INFO',
            'test_coverage': True
        }
    },
    'production': {
        'name': '生产环境',
        'description': '用于正式运行和验收测试',
        'resources': {
            'cpu': '16核',
            'memory': '32GB',
            'storage': '1TB',
            'network': '10Gbps'
        },
        'configuration': {
            'debug_mode': False,
            'logging_level': 'WARN',
            'test_coverage': False
        }
    }
}

# 初始化日志配置
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info("中医古籍测试套件模块已初始化")

# 版本兼容性声明
VERSION_COMPATIBILITY = {
    'python': '>=3.8',
    'numpy': '>=1.21.0',
    'pandas': '>=1.3.0',
    'torch': '>=1.9.0',
    'transformers': '>=4.20.0',
    'networkx': '>=2.6.0'
}

# 测试报告模板
TEST_REPORT_TEMPLATES = {
    'academic_paper': {
        'title': '中医古籍全自动研究系统测试报告',
        'sections': [
            'abstract',
            'introduction',
            'methodology',
            'results',
            'discussion',
            'conclusion',
            'references'
        ],
        'standards': ['T/C IATCM 098-2023', 'GB/T 7714-2015']
    },
    'technical_report': {
        'title': '系统测试技术报告',
        'sections': [
            'executive_summary',
            'test_overview',
            'test_results',
            'analysis',
            'recommendations',
            'appendices'
        ],
        'standards': ['ISO 21000', 'IEEE 830']
    }
}

# 测试套件运行配置
RUNTIME_CONFIG = {
    'max_concurrent_tests': 4,
    'timeout_seconds': 300,
    'retry_attempts': 3,
    'parallel_execution': True,
    'test_reporting': {
        'html_report': True,
        'json_report': True,
        'csv_report': False,
        'email_notification': False
    }
}
