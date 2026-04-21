# src/core/module_status.py
"""
模块状态与优先级枚举定义。

单一真相来源（Single Source of Truth）。
module_base.py 和 module_interface.py 均从此处导入，消除双定义问题。
"""

from enum import Enum


class ModuleStatus(str, Enum):
    """模块状态枚举（继承 str 以支持直接字符串比较）"""
    CREATED = "created"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    ACTIVATING = "activating"
    ACTIVE = "active"
    DEACTIVATING = "deactivating"
    INACTIVE = "inactive"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    ERROR = "error"
    # 兼容旧代码中使用的字符串值
    CLEANED = "cleaned"
    COMPLETED = "completed"


class ModulePriority(str, Enum):
    """模块优先级枚举（继承 str 以支持直接字符串比较）"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
