"""兼容层 — 已迁移至 src.generation.report_generator"""
import warnings as _w
_w.warn(
    'src.output.report_generator 已迁移至 src.generation.report_generator，请更新导入路径',
    DeprecationWarning,
    stacklevel=2,
)
from src.generation.report_generator import *  # noqa: F401,F403
from src.generation.report_generator import Report, ReportFormat, ReportGenerator
