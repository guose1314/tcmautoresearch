# cycle/__init__.py
"""
中医古籍全自动研究系统 - 专业学术迭代循环初始化文件
"""

__version__ = "2.0.0"
__author__ = "中医古籍全自动研究团队"
__description__ = "基于AI的中医古籍智能研究迭代循环系统"

# 导入主要类和函数
from .fixing_stage import FixingStage, RepairAction
from .iteration_cycle import (
    CycleStatus,
    IterationConfig,
    IterationCycle,
    IterationResult,
)
from .module_iteration import ModuleIterationCycle, ModuleIterationResult
from .test_driven_iteration import (
    TestDrivenIteration,
    TestDrivenIterationManager,
    TestResult,
)

try:
    from .system_iteration import SystemIterationCycle, SystemIterationResult
except Exception:  # pragma: no cover - 仅用于可选依赖降级
    SystemIterationCycle = None
    SystemIterationResult = None

# 模块导出
__all__ = [
    'IterationCycle',
    'IterationResult',
    'IterationConfig',
    'CycleStatus',
    'ModuleIterationCycle',
    'ModuleIterationResult',
    'TestDrivenIteration',
    'TestDrivenIterationManager',
    'TestResult',
    'FixingStage',
    'RepairAction'
]

if SystemIterationCycle is not None and SystemIterationResult is not None:
    __all__.extend(['SystemIterationCycle', 'SystemIterationResult'])

# 系统配置
SYSTEM_CONFIG = {
    'iteration_framework': {
        'name': '中医古籍全自动研究迭代框架',
        'version': '2.0.0',
        'standards': ['T/C IATCM 098-2023', 'GB/T 15657', 'ISO 21000'],
        'principles': [
            '系统性原则',
            '科学性原则', 
            '实用性原则',
            '创新性原则'
        ]
    },
    'iteration_phases': [
        'GENERATE',
        'TEST',
        'FIX',
        'ANALYZE',
        'OPTIMIZE',
        'VALIDATE'
    ],
    'academic_levels': {
        'basic': '基础研究',
        'applied': '应用研究',
        'innovative': '创新研究',
        'comprehensive': '综合研究'
    },
    'evaluation_metrics': {
        'scientific_validity': 0.3,
        'methodological_quality': 0.25,
        'innovation_degree': 0.2,
        'practical_value': 0.25
    },
    'performance_target': {
        'max_iterations': 10,
        'timeout_seconds': 300,
        'max_concurrent_tasks': 4,
        'min_confidence_threshold': 0.7
    }
}

# 迭代模式
ITERATION_MODES = {
    'sequential': {
        'name': '顺序迭代',
        'description': '严格按照顺序执行生成-测试-修复流程',
        'characteristics': ['线性执行', '易于控制', '稳定可靠']
    },
    'parallel': {
        'name': '并行迭代',
        'description': '多任务并行执行，提高处理效率',
        'characteristics': ['并行处理', '高吞吐量', '资源优化']
    },
    'adaptive': {
        'name': '自适应迭代',
        'description': '根据执行结果动态调整迭代策略',
        'characteristics': ['智能决策', '动态优化', '自适应调整']
    }
}

# 学术规范
ACADEMIC_STANDARDS = {
    'ethics': {
        'data_privacy': '严格遵守数据隐私保护规定',
        'research_integrity': '确保研究过程的客观性和真实性',
        'citation_standard': '遵循GB/T 7714-2015标准'
    },
    'quality_control': {
        'peer_review': '实施同行评议制度',
        'reproducibility': '确保研究结果可重现',
        'validation': '建立多维度验证机制'
    },
    'publication_requirements': {
        'journal_standards': ['SCI', 'EI', '核心期刊'],
        'format_requirements': ['学术论文', '研究报告', '技术报告'],
        'review_process': ['初审', '外审', '终审']
    }
}

# 初始化日志配置
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.info("中医古籍迭代循环模块已初始化")

# 版本兼容性声明
VERSION_COMPATIBILITY = {
    'python': '>=3.8',
    'numpy': '>=1.21.0',
    'pandas': '>=1.3.0',
    'torch': '>=1.9.0',
    'transformers': '>=4.20.0',
    'networkx': '>=2.6.0'
}

# 迭代循环配置
DEFAULT_ITERATION_CONFIG = {
    'max_iterations': 10,
    'timeout_seconds': 300,
    'enable_auto_repair': True,
    'enable_performance_monitoring': True,
    'enable_test_coverage': True,
    'auto_retry_attempts': 3,
    'confidence_threshold': 0.7,
    'quality_assurance_level': 'high'
}
