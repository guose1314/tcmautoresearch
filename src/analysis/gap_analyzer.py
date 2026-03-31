"""兼容层：请改用 src.research.gap_analyzer。"""

from src.research import gap_analyzer as _research_gap_analyzer

GapAnalyzer = _research_gap_analyzer.GapAnalyzer
GapAnalyzerConfig = _research_gap_analyzer.GapAnalyzerConfig
GapAnalysisRequest = _research_gap_analyzer.GapAnalysisRequest
GapAnalysisResult = _research_gap_analyzer.GapAnalysisResult
GapAnalysisCore = _research_gap_analyzer.GapAnalysisCore
GapAnalysisLLMAdapter = _research_gap_analyzer.GapAnalysisLLMAdapter

__all__ = [
    "GapAnalyzer",
    "GapAnalyzerConfig",
    "GapAnalysisRequest",
    "GapAnalysisResult",
    "GapAnalysisCore",
    "GapAnalysisLLMAdapter",
]