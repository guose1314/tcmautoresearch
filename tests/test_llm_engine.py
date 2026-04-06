import os
import sys
import types
import unittest
from unittest.mock import patch

from src.llm.llm_engine import LLMEngine, setup_cuda_dll_paths
from src.research.gap_analyzer import GapAnalyzer


class _FakeLlama:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def create_chat_completion(self, messages, temperature, max_tokens):
        _ = messages, temperature, max_tokens
        return {"choices": [{"message": {"content": "mocked reply"}}]}


class TestLLMEngine(unittest.TestCase):
    def test_setup_cuda_dll_paths_non_windows(self):
        with patch("src.llm.llm_engine.sys.platform", "linux"):
            self.assertTrue(setup_cuda_dll_paths())

    def test_setup_cuda_dll_paths_windows_registers_bin(self):
        original_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = "C:\\base"
            with patch("src.llm.llm_engine.sys.platform", "win32"), \
                 patch("site.getsitepackages", return_value=["C:/sp"]), \
                 patch("src.llm.llm_engine.glob.glob", return_value=["C:/sp/nvidia/cublas/bin"]), \
                 patch("src.llm.llm_engine.os.path.isdir", return_value=True), \
                 patch("src.llm.llm_engine.os.add_dll_directory", create=True) as mock_add_dll:
                self.assertTrue(setup_cuda_dll_paths())
                self.assertIn("C:/sp/nvidia/cublas/bin", os.environ["PATH"])
                mock_add_dll.assert_called_once_with("C:/sp/nvidia/cublas/bin")
        finally:
            os.environ["PATH"] = original_path

    def test_setup_cuda_dll_paths_windows_no_site_packages(self):
        with patch("src.llm.llm_engine.sys.platform", "win32"), \
             patch("site.getsitepackages", side_effect=RuntimeError("boom")):
            self.assertFalse(setup_cuda_dll_paths())

    def test_load_missing_model_raises(self):
        engine = LLMEngine(model_path="missing.gguf")
        with patch("src.llm.llm_engine.os.path.isfile", return_value=False):
            with self.assertRaises(FileNotFoundError):
                engine.load()

    def test_generate_requires_load(self):
        engine = LLMEngine(model_path="dummy.gguf")
        with self.assertRaises(RuntimeError):
            engine.generate("hi")

    def test_load_generate_and_unload(self):
        engine = LLMEngine(model_path="dummy.gguf", n_gpu_layers=0)
        fake_module = types.SimpleNamespace(Llama=_FakeLlama)

        with patch("src.llm.llm_engine.os.path.isfile", return_value=True), \
             patch("src.llm.llm_engine.setup_cuda_dll_paths", return_value=True), \
             patch.dict(sys.modules, {"llama_cpp": fake_module}):
            engine.load()
            self.assertIsNotNone(engine._llm)
            reply = engine.generate("列出五味子作用")
            self.assertEqual(reply, "mocked reply")
            engine.unload()
            self.assertIsNone(engine._llm)

    def test_load_import_error_raises(self):
        engine = LLMEngine(model_path="dummy.gguf")
        real_import = __import__

        def _guarded_import(name, *args, **kwargs):
            if name == "llama_cpp":
                raise ImportError("missing")
            return real_import(name, *args, **kwargs)

        with patch("src.llm.llm_engine.os.path.isfile", return_value=True), \
             patch("src.llm.llm_engine.setup_cuda_dll_paths", return_value=True), \
             patch("builtins.__import__", side_effect=_guarded_import):
            with self.assertRaises(ImportError):
                engine.load()

    def test_load_skips_when_already_loaded(self):
        engine = LLMEngine(model_path="dummy.gguf")
        engine._llm = object()
        engine.load()
        self.assertIsNotNone(engine._llm)

    def test_generate_with_system_prompt(self):
        engine = LLMEngine(model_path="dummy.gguf")
        fake = _FakeLlama()
        engine._llm = fake
        reply = engine.generate("u", system_prompt="s")
        self.assertEqual(reply, "mocked reply")

    def test_clinical_gap_analysis_uses_generate(self):
        engine = LLMEngine(model_path="dummy.gguf")
        with patch.object(GapAnalyzer, "analyze", return_value="gap report") as mock_analyze:
            result = engine.clinical_gap_analysis(
                clinical_question="中医干预证据缺口是什么？",
                evidence_matrix={"record_count": 1},
                literature_summaries=[{"title": "A", "summary_text": "B"}],
                output_language="zh",
            )

        self.assertEqual(result, "gap report")
        self.assertEqual(mock_analyze.call_count, 1)
        self.assertEqual(mock_analyze.call_args.kwargs["clinical_question"], "中医干预证据缺口是什么？")

    def test_research_helpers_delegate_generate(self):
        engine = LLMEngine(model_path="dummy.gguf")
        with patch.object(engine, "generate", return_value="ok") as mock_generate:
            engine.generate_research_hypothesis("中医", "摘要", "已有研究")
            engine.suggest_paper_ideas(
                {"entities": [1], "top_herbs": ["甘草"], "top_syndromes": ["气虚"]},
                "临床问题",
            )
            engine.draft_section("Methods", {"k": "v"})

        self.assertEqual(mock_generate.call_count, 3)


if __name__ == "__main__":
    unittest.main()
