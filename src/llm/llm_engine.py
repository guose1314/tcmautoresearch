# src/llm/llm_engine.py
"""
本地 LLM 推理引擎
- 自动检测并注册 NVIDIA CUDA DLL 路径（cublas64_12.dll 等）
- 基于 llama-cpp-python 加载 GGUF 格式模型
- 支持 GPU 层卸载（n_gpu_layers=-1 全量卸载到 RTX 4060）
- 提供 TCM 科研专用 Prompt 模板
"""

import glob
import logging
import os
import sys
from pathlib import Path
from typing import Any

from src.research.gap_analyzer import GapAnalyzer

logger = logging.getLogger(__name__)

# 默认模型路径（相对项目根）
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "qwen1_5-7b-chat-q8_0.gguf"
# 项目根，用于把配置里写的相对路径（如 "./models/..."）锚定到仓库根，
# 避免随启动 cwd 变化导致 FileNotFoundError。
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_model_path(path: str | None) -> str:
    """把 model_path 解析成绝对路径。

    - 为空 → 使用 DEFAULT_MODEL_PATH。
    - 已是绝对路径 → 原样返回。
    - 相对路径 → 锚定到项目根，避免依赖运行 cwd。
    """
    if not path:
        return str(DEFAULT_MODEL_PATH)
    p = Path(path)
    if not p.is_absolute():
        p = (_PROJECT_ROOT / p).resolve()
    return str(p)


def setup_cuda_dll_paths() -> bool:
    """
    将 nvidia-cublas-cu12 / nvidia-cuda-runtime-cu12 的 bin 目录
    加入 Windows PATH 和 Python DLL 搜索路径。

    必须在 ``import llama_cpp`` 之前调用。

    Returns:
        bool: 找到并注册了 CUDA DLL 目录时返回 True。
    """
    if sys.platform != "win32":
        return True  # Linux/macOS 不需要手动处理

    # 从当前 venv 或系统 site-packages 查找 nvidia 包
    try:
        import site as _site
        site_pkgs = _site.getsitepackages()
    except Exception:
        site_pkgs = []

    found = False
    for sp in site_pkgs:
        nvidia_base = os.path.join(sp, "nvidia")
        if not os.path.isdir(nvidia_base):
            continue
        for bin_dir in glob.glob(os.path.join(nvidia_base, "**", "bin"), recursive=True):
            if os.path.isdir(bin_dir):
                # 加入 PATH（供 Windows OS 加载器解析 DLL 依赖链）
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                # 加入 Python DLL 搜索目录
                if hasattr(os, "add_dll_directory"):
                    os.add_dll_directory(bin_dir)
                found = True
                logger.debug("CUDA DLL 目录已注册: %s", bin_dir)
    return found


class LLMEngine:
    """
    封装本地 GGUF 模型推理，通过 llama-cpp-python 调用。

    RTX 4060 Laptop GPU（8 GB VRAM）全量加载 Qwen1.5-7B-Chat Q8_0 约需 7.5 GB，
    建议 n_gpu_layers=-1（全量 GPU）或设置具体层数保留 CPU 余量。

    Usage::

        engine = LLMEngine()
        engine.load()
        reply = engine.generate("请列举五味子的性味归经。")
        print(reply)
        engine.unload()
    """

    def __init__(
        self,
        model_path: str | None = None,
        n_gpu_layers: int = -1,
        n_ctx: int = 4096,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        verbose: bool = False,
    ):
        """
        Args:
            model_path: GGUF 模型文件路径，默认使用项目 models/ 目录下的 Qwen 模型。
            n_gpu_layers: GPU 卸载层数。-1 = 全量卸载；0 = 纯 CPU。
            n_ctx: 上下文窗口长度（token 数）。
            temperature: 采样温度，值越低越确定。
            max_tokens: 单次生成最大 token 数。
            verbose: 是否输出 llama.cpp 底层日志。
        """
        self.model_path = _resolve_model_path(model_path)
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.verbose = verbose
        self._llm: Any = None

    def load(self) -> None:
        """加载模型到内存（GPU/CPU）。"""
        if self._llm is not None:
            logger.warning("模型已加载，跳过重复加载。")
            return

        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(f"模型文件不存在: {self.model_path}")

        # 必须在首次 import llama_cpp 之前完成 DLL 注册
        setup_cuda_dll_paths()

        try:
            from llama_cpp import Llama  # noqa: PLC0415  (late import by design)
        except ImportError as exc:
            raise ImportError(
                "llama-cpp-python 未安装或 CUDA DLL 缺失。"
                "请确认使用 venv310 环境运行，并已安装 nvidia-cublas-cu12。"
            ) from exc

        logger.info(
            "加载模型: %s  (n_gpu_layers=%s, n_ctx=%d)",
            self.model_path,
            self.n_gpu_layers,
            self.n_ctx,
        )
        self._llm = Llama(
            model_path=self.model_path,
            n_gpu_layers=self.n_gpu_layers,
            n_ctx=self.n_ctx,
            verbose=self.verbose,
        )
        logger.info("模型加载完成。")

    def unload(self) -> None:
        """释放模型内存。"""
        self._llm = None
        logger.info("模型已卸载。")

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """
        执行单轮生成（ChatML 格式，兼容 Qwen 系列）。

        Args:
            prompt: 用户输入。
            system_prompt: 可选系统提示词。

        Returns:
            str: 模型生成的文本。
        """
        if self._llm is None:
            raise RuntimeError("请先调用 load() 加载模型。")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._llm.create_chat_completion(
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response["choices"][0]["message"]["content"]

    # ------------------------------------------------------------------
    # TCM 科研专用便捷方法
    # ------------------------------------------------------------------

    def generate_research_hypothesis(
        self, domain: str, corpus_summary: str, existing_research: str = ""
    ) -> str:
        """根据语料摘要生成中医科研假设。"""
        system = (
            "你是一位中医古籍研究专家，熟悉《伤寒论》《本草纲目》《黄帝内经》等经典，"
            "擅长从古籍文本分析中提炼具有SCI发表价值的科研假设。"
        )
        user = (
            f"研究领域：{domain}\n"
            f"语料分析摘要：{corpus_summary}\n"
        )
        if existing_research:
            user += f"已有研究背景：{existing_research}\n"
        user += (
            "\n请根据以上信息，提出3个具体的、可验证的研究假设，"
            "每个假设包含：①假设陈述 ②研究意义 ③验证方案。"
        )
        return self.generate(user, system)

    def suggest_paper_ideas(
        self, analysis_result: dict, clinical_problem: str
    ) -> str:
        """结合古籍分析结果与临床问题，生成论文选题建议。"""
        system = (
            "你是中医临床研究方法学专家，"
            "擅长将古籍文本挖掘结果与现代临床问题结合，找到SCI期刊的发表切入点。"
        )
        entities_summary = (
            f"提取实体数量：{len(analysis_result.get('entities', []))} 个\n"
            f"高频药物：{analysis_result.get('top_herbs', [])}\n"
            f"主要证候：{analysis_result.get('top_syndromes', [])}\n"
        )
        user = (
            f"古籍分析结果：\n{entities_summary}\n"
            f"临床问题：{clinical_problem}\n"
            "\n请提出3个可发表于中医/中西医结合SCI期刊的论文题目，"
            "每条包含：①题目 ②期刊方向 ③核心创新点。"
        )
        return self.generate(user, system)

    def draft_section(
        self, section: str, context_data: dict
    ) -> str:
        """
        生成论文指定章节草稿。

        Args:
            section: 章节名，如 'Introduction', 'Methods', 'Results', 'Discussion'。
            context_data: 包含分析结果的字典。
        """
        system = (
            "你是一位中医药学科研写作助手，"
            "熟悉SCI论文写作规范，文风严谨、客观、符合学术期刊要求。"
        )
        user = (
            f"请为以下中医古籍研究撰写论文的 {section} 部分草稿（中文，约400字）。\n"
            f"研究数据摘要：\n{context_data}\n"
            "要求：结构清晰，引用数据有据可查，避免主观修辞。"
        )
        return self.generate(user, system)

    def clinical_gap_analysis(
        self,
        clinical_question: str,
        evidence_matrix: dict,
        literature_summaries: list[dict],
        output_language: str = "zh",
    ) -> str:
        """
        基于证据矩阵执行临床关联 Gap Analysis。

        Args:
            clinical_question: 临床问题（PICO 或自由文本）。
            evidence_matrix: 结构化证据矩阵。
            literature_summaries: 文献摘要列表。
            output_language: 输出语言，默认中文。
        """
        analyzer = GapAnalyzer(llm_service=self)
        return analyzer.analyze(
            clinical_question=clinical_question,
            evidence_matrix=evidence_matrix,
            literature_summaries=literature_summaries,
            output_language=output_language,
        )
