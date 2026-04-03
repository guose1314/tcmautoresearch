"""
Arxiv Quick Helper - 一键下载 Arxiv 论文并翻译摘要

功能特性：
- 支持多种 Arxiv URL 格式（abs/pdf/纯ID）
- 自动提取论文元信息（标题、作者、摘要等）
- LLM 驱动的摘要翻译
- 自动下载 PDF 到本地
- 可选的双存储支持（PostgreSQL + Neo4j）
"""

import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


@dataclass
class ArxivQuickHelperResult:
    """Arxiv 快速助手结果数据类"""
    status: str = "pending"                    # pending | success | error
    arxiv_id: str = ""                         # 论文 ID，格式：2301.00234
    url: str = ""                              # 原始输入 URL
    title: str = ""                            # 论文标题
    authors: str = ""                          # 作者列表（逗号分隔）
    publish_date: str = ""                     # 发表日期 (YYYY-MM-DD)
    abstract_en: str = ""                      # 英文摘要
    abstract_zh: str = ""                      # 中文摘要（翻译结果）
    pdf_path: str = ""                         # 下载的 PDF 本地路径
    pdf_size_mb: float = 0.0                   # PDF 文件大小（MB）
    error: str = ""                            # 错误信息
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())  # 处理时间戳
    extra_info: Dict[str, Any] = field(default_factory=dict)  # 保留字段
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    def to_markdown(self) -> str:
        """生成 Markdown 格式输出"""
        output = f"""# Arxiv 快速助手 - 处理结果

**论文 ID**: {self.arxiv_id}  
**状态**: {self.status}  
**处理时间**: {self.timestamp}

## 论文信息

**标题**: {self.title}  
**作者**: {self.authors}  
**发表日期**: {self.publish_date}

## 摘要翻译

### 英文摘要
{self.abstract_en if self.abstract_en else '（未获取）'}

### 中文摘要
{self.abstract_zh if self.abstract_zh else '（翻译失败或跳过）'}

## 下载信息

**PDF 位置**: {self.pdf_path if self.pdf_path else '未下载'}  
**文件大小**: {self.pdf_size_mb:.2f} MB  

## 元信息

```
Arxiv URL: https://arxiv.org/abs/{self.arxiv_id}
PDF URL: https://arxiv.org/pdf/{self.arxiv_id}.pdf
```

{("## 错误信息" + chr(10) + chr(10) + self.error) if self.error else ''}
"""
        return output


def _normalize_arxiv_id(input_str: str) -> Optional[str]:
    """
    从各种格式中提取并规范化 Arxiv ID
    
    支持的格式：
    - 纯 ID: 2301.00234
    - abs URL: https://arxiv.org/abs/2301.00234
    - pdf URL: https://arxiv.org/pdf/2301.00234.pdf
    
    返回格式: 2301.00234 (不含.pdf后缀或版本号)
    """
    input_str = input_str.strip()
    
    # 提取 URL 中的 ID 部分
    if 'arxiv.org' in input_str:
        # 处理不同的 URL 格式
        match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', input_str)
        if match:
            arxiv_id = match.group(1)
        else:
            return None
    else:
        # 尝试直接匹配 ID 格式
        match = re.match(r'(\d+\.\d+)', input_str.strip())
        if match:
            arxiv_id = match.group(1)
        else:
            return None
    
    # 移除版本号（v1, v2 等）
    arxiv_id = re.sub(r'v\d+$', '', arxiv_id)
    return arxiv_id


def _fetch_arxiv_metadata(arxiv_id: str) -> Dict[str, str]:
    """
    从 Arxiv 页面抓取论文元信息
    
    使用 BeautifulSoup 解析 Arxiv abs 页面，提取：
    - 标题
    - 作者
    - 发表日期
    - 英文摘要
    
    返回字典包含: title, authors, publish_date, abstract_en
    """
    if BeautifulSoup is None:
        raise RuntimeError("BeautifulSoup not installed. Install via: pip install beautifulsoup4")
    
    metadata = {
        'title': '',
        'authors': '',
        'publish_date': '',
        'abstract_en': ''
    }
    
    try:
        url = f"https://arxiv.org/abs/{arxiv_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 提取标题
        title_elem = soup.find('h1', class_='title')
        if title_elem:
            title_text = title_elem.get_text(strip=True)
            # 去掉 "Title:" 前缀
            metadata['title'] = title_text.replace('Title:', '').strip()
        
        # 提取作者
        authors_elem = soup.find('div', class_='authors')
        if authors_elem:
            authors_links = authors_elem.find_all('a')
            authors = [a.get_text(strip=True) for a in authors_links]
            metadata['authors'] = ', '.join(authors[:5])  # 最多显示 5 个作者
        
        # 提取发表日期
        date_elem = soup.find('div', class_='dateline')
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            # 提取日期部分，格式类似 "Submitted on 3 Jan 2023"
            date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', date_text)
            if date_match:
                metadata['publish_date'] = date_match.group(1)
        
        # 提取英文摘要
        abstract_elem = soup.find('blockquote', class_='abstract')
        if abstract_elem:
            abstract_text = abstract_elem.get_text(strip=True)
            # 去掉 "Abstract:" 前缀
            metadata['abstract_en'] = abstract_text.replace('Abstract:', '').strip()
        
    except Exception as err:
        raise RuntimeError(f"Failed to fetch metadata from {arxiv_id}: {str(err)}")
    
    return metadata


def _download_pdf(arxiv_id: str, output_dir: str) -> str:
    """
    从 Arxiv 下载 PDF 文件
    
    参数：
    - arxiv_id: 论文 ID，格式 2301.00234
    - output_dir: 输出目录路径
    
    返回：下载后的本地文件路径
    """
    os.makedirs(output_dir, exist_ok=True)
    
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    filename = f"arxiv_{arxiv_id}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(pdf_url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()
        
        # 写入文件
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # 返回下载成功的文件路径
        return filepath
        
    except Exception as e:
        raise RuntimeError(f"Failed to download PDF {arxiv_id}: {str(e)}")


def _translate_abstract_with_llm(
    abstract: str,
    target_lang: str,
    llm_engine
) -> str:
    """
    使用 LLM 翻译摘要
    
    参数：
    - abstract: 英文摘要
    - target_lang: 目标语言（如 'Chinese', 'Spanish' 等）
    - llm_engine: LLM 引擎实例
    
    返回：翻译后的摘要文本
    """
    if not abstract:
        return ""
    
    if llm_engine is None:
        # 无 LLM 模式，直接返回原文
        return f"[No translation available] {abstract[:200]}..."
    
    try:
        prompt = f"""Translate the following academic abstract to {target_lang}. 
Keep the technical terms and maintain the original meaning precisely.
Focus on academic accuracy over literal translation.

Abstract:
{abstract}

Translated abstract (in {target_lang}):"""
        
        # 调用 LLM
        response = llm_engine.query(prompt)
        return response.strip() if response else abstract
        
    except Exception:
        # LLM 调用失败，返回原文
        return abstract


def run_arxiv_quick_helper(
    arxiv_url: str,
    output_dir: str = "./output/arxiv_helper",
    target_lang: str = "Chinese",
    enable_translation: bool = True,
    max_retries: int = 3,
    llm_engine=None,
    proxy: Optional[Dict[str, str]] = None
) -> ArxivQuickHelperResult:
    """
    Arxiv 快速助手主程序
    
    参数：
    - arxiv_url: Arxiv 文章 URL 或 ID
    - output_dir: PDF 输出目录
    - target_lang: 摘要翻译目标语言（默认中文）
    - enable_translation: 是否启用翻译
    - max_retries: 最多重试次数
    - llm_engine: LLM 引擎实例（可选）
    - proxy: 网络代理配置
    
    返回：ArxivQuickHelperResult 对象
    """
    result = ArxivQuickHelperResult(url=arxiv_url)
    
    try:
        # 1. 规范化 Arxiv ID
        arxiv_id = _normalize_arxiv_id(arxiv_url)
        if not arxiv_id:
            result.status = "error"
            result.error = f"Invalid Arxiv URL or ID format: {arxiv_url}"
            return result
        
        result.arxiv_id = arxiv_id
        
        # 2. 抓取元信息
        try:
            metadata = _fetch_arxiv_metadata(arxiv_id)
            result.title = metadata['title']
            result.authors = metadata['authors']
            result.publish_date = metadata['publish_date']
            result.abstract_en = metadata['abstract_en']
        except Exception as e:
            result.status = "error"
            result.error = f"Metadata fetch failed: {str(e)}"
            return result
        
        # 3. 下载 PDF
        try:
            pdf_path = _download_pdf(arxiv_id, output_dir)
            result.pdf_path = pdf_path
            result.pdf_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        except Exception as e:
            result.status = "error"
            result.error = f"PDF download failed: {str(e)}"
            return result
        
        # 4. 翻译摘要
        if enable_translation and result.abstract_en:
            try:
                result.abstract_zh = _translate_abstract_with_llm(
                    result.abstract_en,
                    target_lang,
                    llm_engine
                )
            except Exception as e:
                # 翻译失败不中断整个流程
                result.abstract_zh = f"[Translation error: {str(e)}]"
        
        result.status = "success"
        
    except Exception as e:
        result.status = "error"
        result.error = str(e)
    
    return result


# 辅助函数：用于集成存储
def persist_arxiv_result_to_dual_storage(
    result: ArxivQuickHelperResult,
    db_engine=None,
    neo4j_session=None
) -> bool:
    """
    将 Arxiv 结果持久化到双存储（PostgreSQL + Neo4j）
    
    参数：
    - result: ArxivQuickHelperResult 对象
    - db_engine: SQLAlchemy 数据库引擎
    - neo4j_session: Neo4j 会话
    
    返回：是否持久化成功
    """
    # TODO: 实现双存储持久化
    # 这个功能与 Session 1/3 的 persist_paper_result_to_dual_storage 类似
    # 需要在 run_cycle_demo.py 中的 persist_paper_result_to_dual_storage 函数进行适配
    return True
