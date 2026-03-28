"""Arxiv fine translation adapter (Docker service compatible)."""

from __future__ import annotations

import io
import json
import pickle
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from pydantic import BaseModel, Field


class DockerServiceApiComModel(BaseModel):
    """Compatible payload model for GPT-Academic DaaS stream API."""

    client_command: Optional[str] = Field(default=None)
    client_file_attach: Optional[dict] = Field(default=None)
    server_message: Optional[Any] = Field(default=None)
    server_std_err: Optional[str] = Field(default=None)
    server_std_out: Optional[str] = Field(default=None)
    server_file_attach: Optional[dict] = Field(default=None)


@dataclass
class ArxivFineTranslationResult:
    status: str
    arxiv_id: str
    input_value: str
    output_files: List[str]
    server_message: str
    server_std_out: str
    server_std_err: str
    summary: str
    translation_excerpt: str
    output_json: str
    output_markdown: str
    error: str = ""


def parse_arxiv_id(value: str) -> str:
    """Extract canonical arXiv ID from ID/url/pdf url."""
    text = (value or "").strip()
    if not text:
        return ""

    patterns = [
        r"arxiv\.org/abs/([a-z\-]+/\d{7}|\d{4}\.\d{4,5})(v\d+)?",
        r"arxiv\.org/pdf/([a-z\-]+/\d{7}|\d{4}\.\d{4,5})(v\d+)?(?:\.pdf)?",
        r"^([a-z\-]+/\d{7}|\d{4}\.\d{4,5})(v\d+)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _process_received(
    received: Any,
    save_file_dir: Path,
    output_manifest: Dict[str, Any],
) -> Dict[str, Any]:
    server_message = getattr(received, "server_message", None)
    server_std_err = getattr(received, "server_std_err", None)
    server_std_out = getattr(received, "server_std_out", None)
    server_file_attach = getattr(received, "server_file_attach", None)

    if server_message:
        output_manifest["server_message"] += str(server_message)
    if server_std_err:
        output_manifest["server_std_err"] += str(server_std_err)
    if server_std_out:
        output_manifest["server_std_out"] += str(server_std_out)

    if isinstance(server_file_attach, dict):
        for file_name, file_content in server_file_attach.items():
            target = save_file_dir / file_name
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as f:
                f.write(file_content)
            output_manifest["server_file_attach"].append(str(target))

    return output_manifest


def run_arxiv_fine_translation_docker(
    arxiv_input: str,
    server_url: str,
    output_dir: str = "./output/arxiv_fine_translation",
    advanced_arg: str = "",
    timeout_sec: int = 1800,
) -> ArxivFineTranslationResult:
    """
    Trigger GPT-Academic style arxiv fine translation over DaaS stream.

    Notes:
    - server_url should be a DaaS endpoint compatible with pickled payload stream.
    - This function is network-side best effort; caller should fallback on failure.
    """
    arxiv_id = parse_arxiv_id(arxiv_input)
    if not arxiv_id:
        return ArxivFineTranslationResult(
            status="failed",
            arxiv_id="",
            input_value=arxiv_input,
            output_files=[],
            server_message="",
            server_std_out="",
            server_std_err="",
            summary="",
            translation_excerpt="",
            output_json="",
            output_markdown="",
            error="无法解析 Arxiv ID，请输入如 2301.00234 或 https://arxiv.org/abs/2301.00234",
        )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    recv_dir = out_dir / f"recv_{arxiv_id}_{ts}"
    recv_dir.mkdir(parents=True, exist_ok=True)

    command = f"把 Arxiv 论文翻译成中文，论文 ID 是 {arxiv_id}，记得用插件！ {advanced_arg}".strip()
    payload_obj = DockerServiceApiComModel(client_command=command)
    pickled_data = pickle.dumps(payload_obj)
    file_obj = io.BytesIO(pickled_data)
    files = {"file": ("docker_service_api_com_model.pkl", file_obj, "application/octet-stream")}

    output_manifest: Dict[str, Any] = {
        "server_message": "",
        "server_std_err": "",
        "server_std_out": "",
        "server_file_attach": [],
    }

    try:
        response = requests.post(
            server_url,
            files=files,
            stream=True,
            timeout=(30, timeout_sec),
        )
        if response.status_code != 200:
            return ArxivFineTranslationResult(
                status="failed",
                arxiv_id=arxiv_id,
                input_value=arxiv_input,
                output_files=[],
                server_message="",
                server_std_out="",
                server_std_err="",
                summary="",
                translation_excerpt="",
                output_json="",
                output_markdown="",
                error=f"DaaS 请求失败: HTTP {response.status_code} {response.text[:300]}",
            )

        chunk_buf: Optional[bytes] = None
        max_full_package_size = 1024 * 1024 * 1024
        for chunk in response.iter_content(max_full_package_size):
            if not chunk:
                continue
            chunk_buf = chunk if chunk_buf is None else chunk_buf + chunk
            if chunk_buf is None:
                continue
            try:
                received = pickle.loads(chunk_buf)
                chunk_buf = None
                output_manifest = _process_received(received, recv_dir, output_manifest)
            except Exception:
                continue

        summary = output_manifest["server_message"][:1200]
        excerpt_src = output_manifest["server_std_out"] or output_manifest["server_message"]
        translation_excerpt = excerpt_src[:1200]

        result_obj = {
            "timestamp": datetime.now().isoformat(),
            "input": arxiv_input,
            "arxiv_id": arxiv_id,
            "server_url": server_url,
            "output_files": output_manifest["server_file_attach"],
            "server_message": output_manifest["server_message"],
            "server_std_out": output_manifest["server_std_out"],
            "server_std_err": output_manifest["server_std_err"],
            "summary": summary,
            "translation_excerpt": translation_excerpt,
        }

        json_path = out_dir / f"arxiv_fine_translation_{arxiv_id}_{ts}.json"
        md_path = out_dir / f"arxiv_fine_translation_{arxiv_id}_{ts}.md"
        json_path.write_text(json.dumps(result_obj, ensure_ascii=False, indent=2), encoding="utf-8")

        file_lines = "\n".join(f"- {p}" for p in output_manifest["server_file_attach"]) or "- (无附件)"
        md_text = (
            "# Arxiv 精细翻译（Docker）结果\n\n"
            f"- Arxiv ID: {arxiv_id}\n"
            f"- 服务端点: {server_url}\n"
            f"- 时间: {result_obj['timestamp']}\n\n"
            "## 产物文件\n\n"
            f"{file_lines}\n\n"
            "## 服务消息\n\n"
            f"{output_manifest['server_message'][:6000]}\n\n"
            "## 标准输出\n\n"
            f"{output_manifest['server_std_out'][:4000]}\n\n"
            "## 标准错误\n\n"
            f"{output_manifest['server_std_err'][:4000]}\n"
        )
        md_path.write_text(md_text, encoding="utf-8")

        return ArxivFineTranslationResult(
            status="completed",
            arxiv_id=arxiv_id,
            input_value=arxiv_input,
            output_files=output_manifest["server_file_attach"],
            server_message=output_manifest["server_message"],
            server_std_out=output_manifest["server_std_out"],
            server_std_err=output_manifest["server_std_err"],
            summary=summary,
            translation_excerpt=translation_excerpt,
            output_json=str(json_path),
            output_markdown=str(md_path),
        )
    except Exception as exc:
        return ArxivFineTranslationResult(
            status="failed",
            arxiv_id=arxiv_id,
            input_value=arxiv_input,
            output_files=[],
            server_message="",
            server_std_out="",
            server_std_err="",
            summary="",
            translation_excerpt="",
            output_json="",
            output_markdown="",
            error=str(exc),
        )
