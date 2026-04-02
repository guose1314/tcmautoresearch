# core/__init__.py
"""
中医古籍全自动研究系统 - 专业学术核心模块初始化文件
"""

import logging

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "基于T/C IATCM 098-2023标准的中医古籍研究系统核心模块"

# 导入主要类和函数
from .algorithm_optimizer import AlgorithmOptimizer
from .architecture import ModuleRegistry, SystemArchitecture
from .event_bus import EventBus

# BaseModule is the recommended base class for all modules.
from .module_base import BaseModule
from .module_factory import ModuleFactory

# ModuleInterface and its data classes are kept for backward compatibility.
# New code should inherit BaseModule directly.
from .module_interface import (
    ModuleContext,
    ModuleInterface,
    ModuleOutput,
    ModulePriority,
    ModuleStatus,
)

# 模块导出
__all__ = [
    # Recommended
    'BaseModule',
    'SystemArchitecture',
    'AlgorithmOptimizer',
    'ModuleRegistry',
    'EventBus',
    'ModuleFactory',
    # Deprecated — kept for backward compatibility
    'ModuleInterface',
    'ModuleContext',
    'ModuleOutput',
    'ModuleStatus',
    'ModulePriority',
]

# 核心系统配置
CORE_SYSTEM_CONFIG = {
    'system_info': {
        'name': '中医古籍全自动研究系统',
        'version': '2.0.0',
        'standards': ['T/C IATCM 098-2023', 'GB/T 15657', 'ISO 21000'],
        'principles': [
            '系统性原则',
            '科学性原则', 
            '实用性原则',
            '创新性原则'
        ]
    },
    'module_architecture': {
        'module_types': [
            'preprocessing',
            'extraction',
            'modeling',
            'reasoning',
            'output',
            'learning',
            'analysis',
            'research'
        ],
        'dependency_graph': {
            'preprocessing': ['input'],
            'extraction': ['preprocessing'],
            'modeling': ['extraction'],
            'reasoning': ['modeling'],
            'output': ['reasoning'],
            'learning': ['output', 'reasoning'],
            'analysis': ['output', 'learning'],
            'research': ['analysis', 'learning']
        }
    },
    'quality_requirements': {
        'scientific_validity': 0.95,
        'methodological_quality': 0.90,
        'reproducibility': 0.95,
        'standard_compliance': 0.98,
        'performance_threshold': 0.85
    },
    'performance_target': {
        'max_processing_time': 300,  # 秒
        'memory_usage_limit': 2048,   # MB
        'concurrent_requests': 10,
        'throughput': 1000  # 处理速度
    }
}

# 模块注册中心配置
MODULE_REGISTRY_CONFIG = {
    'registry_info': {
        'name': '模块注册中心',
        'version': '2.0.0',
        'registration_policy': 'strict',
        'validation_level': 'high'
    },
    'module_validation': {
        'interface_compliance': True,
        'quality_assurance': True,
        'academic_compliance': True,
        'performance_benchmark': True
    },
    'module_lifecycle': {
        'creation': 'created',
        'initialization': 'initialized',
        'activation': 'active',
        'deactivation': 'inactive',
        'termination': 'terminated'
    }
}

# 核心组件配置
CORE_COMPONENTS = {
    'architecture': {
        'name': '系统架构',
        'description': '系统整体架构管理',
        'version': '2.0.0',
        'status': 'active'
    },
    'module_manager': {
        'name': '模块管理器',
        'description': '模块注册、加载和管理',
        'version': '2.0.0',
        'status': 'active'
    },
    'interface_manager': {
        'name': '接口管理器',
        'description': '模块接口标准化管理',
        'version': '2.0.0',
        'status': 'active'
    },
    'performance_monitor': {
        'name': '性能监控器',
        'description': '系统性能实时监控',
        'version': '2.0.0',
        'status': 'active'
    }
}

# 初始化日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info("中医古籍核心模块已初始化")

# 版本兼容性声明
VERSION_COMPATIBILITY = {
    'python': '>=3.8',
    'numpy': '>=1.21.0',
    'pandas': '>=1.3.0',
    'torch': '>=1.9.0',
    'transformers': '>=4.20.0',
    'networkx': '>=2.6.0'
}

# 核心系统指标
CORE_METRICS = {
    'system_health': 0.0,
    'module_compliance': 0.0,
    'performance_score': 0.0,
    'academic_quality': 0.0,
    'resource_utilization': 0.0
}

# 核心系统状态
SYSTEM_STATUS = {
    'initialized': False,
    'running': False,
    'healthy': False,
    'stable': False,
    'secure': False
}

# 系统安全配置
SECURITY_CONFIG = {
    'data_encryption': True,
    'access_control': True,
    'audit_logging': True,
    'data_privacy': True,
    'compliance_monitoring': True
}

# 学术规范配置
ACADEMIC_STANDARDS = {
    'scientific_validity': 0.95,
    'methodological_rigor': 0.90,
    'reproducibility': 0.95,
    'standard_compliance': 0.98,
    'quality_assurance': 0.92
}

# 系统监控配置
MONITORING_CONFIG = {
    'performance_metrics': [
        'cpu_usage',
        'memory_usage', 
        'disk_usage',
        'network_usage',
        'processing_time',
        'throughput'
    ],
    'quality_metrics': [
        'compliance_score',
        'accuracy_score',
        'consistency_score',
        'reliability_score'
    ],
    'academic_metrics': [
        'scientific_validity',
        'methodological_quality',
        'reproducibility',
        'standard_compliance'
    ]
}
