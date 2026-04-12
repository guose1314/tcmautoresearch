"""
run_cycle_demo CLI 参数构建模块。

该模块只负责参数定义，不包含业务执行逻辑。
"""

import argparse
import os
import sys

HELP_SUMMARY = (
    "中医古籍全自动研究系统迭代循环演示\n"
    "Quick helper flags: --enable-arxiv-helper --arxiv-helper-url --arxiv-helper-dir "
    "--arxiv-helper-lang --arxiv-helper-no-translation --arxiv-helper-persist-storage "
    "--enable-scholar-helper --scholar-url --scholar-output-dir --scholar-topic-hint "
    "--scholar-target-lang --scholar-max-papers --scholar-no-llm "
    "--scholar-additional-prompt --scholar-persist-storage"
)


def build_cycle_demo_arg_parser() -> argparse.ArgumentParser:
    """构建 run_cycle_demo 的命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description=HELP_SUMMARY,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument('--config', dest='config_path', type=str, default='config.yml',
                        help='主配置文件路径（默认 config.yml）')
    parser.add_argument('--environment', type=str, default=None,
                        help='目标配置环境；未指定时按配置中心默认值或环境变量解析')
    parser.add_argument('--mode', choices=['demo', 'research'], default='demo',
                        help='运行模式: demo（现有行为）或 research（科研闭环）')
    parser.add_argument('--question', type=str, default='',
                        help='科研闭环模式下的研究问题')
    parser.add_argument('--research-phases', type=str, default='observe',
                        help='科研闭环要执行的阶段，逗号分隔（默认 observe）')
    parser.add_argument('--export-report', action='store_true',
                        help='在 research 模式结束后，基于 session_result 额外导出 IMRD 报告')
    parser.add_argument('--report-format', action='append', choices=['markdown', 'docx'],
                        help='IMRD 报告输出格式，可重复传入；默认 markdown')
    parser.add_argument('--report-output-dir', type=str, default='./output/research_reports',
                        help='IMRD 报告输出目录')
    parser.add_argument('--demo-type', choices=['basic', 'academic', 'performance', 'full'],
                        default='full', help='演示类型')
    parser.add_argument('--iterations', type=int, default=3, help='迭代次数')
    parser.add_argument('--verbose', action='store_true', help='详细输出模式')
    parser.add_argument('--enable-autorresearch', action='store_true', help='在主流程后运行 AutoResearch 循环')
    parser.add_argument('--autorresearch-instruction', type=str,
                        default='请自动优化训练脚本，降低 val_bpb 并控制显存占用。',
                        help='AutoResearch 中文研究指令')
    parser.add_argument('--autorresearch-instruction-file', type=str, default='',
                        help='AutoResearch 中文研究指令文件路径（UTF-8）')
    parser.add_argument('--autorresearch-iters', type=int, default=3,
                        help='AutoResearch 最大迭代轮次')
    parser.add_argument('--autorresearch-timeout', type=int, default=300,
                        help='AutoResearch 每轮训练时限（秒）')
    parser.add_argument('--autorresearch-strategy', choices=['heuristic', 'llm'], default='heuristic',
                        help='AutoResearch 假设生成策略')
    parser.add_argument('--autorresearch-rollback-mode', choices=['restore', 'reset'], default='restore',
                        help='AutoResearch 回滚模式')
    parser.add_argument('--autorresearch-python-exe', type=str, default=sys.executable,
                        help='AutoResearch 运行 Python 解释器路径')
    parser.add_argument('--enable-paper-plugin', action='store_true',
                        help='在主流程后运行论文读取/翻译/摘要插件')
    parser.add_argument('--paper-input', type=str, default='',
                        help='论文输入路径（.pdf/.tex 文件或目录）')
    parser.add_argument('--paper-output-dir', type=str, default='./output/paper_plugin',
                        help='论文插件输出目录')
    parser.add_argument('--paper-translate-lang', type=str, default='中文',
                        help='论文翻译目标语言')
    parser.add_argument('--paper-summary-lang', type=str, default='中文',
                        help='论文摘要输出语言')
    parser.add_argument('--paper-no-llm', action='store_true',
                        help='禁用LLM，仅做抽取式摘要')
    parser.add_argument('--paper-persist-storage', action='store_true',
                        help='将论文插件结果写入 PostgreSQL+Neo4j')
    parser.add_argument('--paper-pg-url', type=str, default='',
                        help='PostgreSQL 完整连接串，优先级高于拆分参数')
    parser.add_argument('--paper-db-host', type=str, default='',
                        help='PostgreSQL 主机，默认读取 DB_HOST 或 localhost')
    parser.add_argument('--paper-db-port', type=str, default='',
                        help='PostgreSQL 端口，默认读取 DB_PORT 或 5432')
    parser.add_argument('--paper-db-user', type=str, default='',
                        help='PostgreSQL 用户，默认读取 DB_USER 或 tcm_user')
    parser.add_argument('--paper-db-password', type=str, default='',
                        help='PostgreSQL 密码，默认读取 DB_PASSWORD')
    parser.add_argument('--paper-db-name', type=str, default='',
                        help='PostgreSQL 数据库名，默认读取 DB_NAME 或 tcm_autoresearch')
    parser.add_argument('--paper-neo4j-uri', type=str, default='',
                        help='Neo4j URI，优先级高于拆分参数')
    parser.add_argument('--paper-neo4j-scheme', type=str, default='',
                        help='Neo4j 协议，默认读取 NEO4J_SCHEME 或 neo4j')
    parser.add_argument('--paper-neo4j-host', type=str, default='',
                        help='Neo4j 主机，默认读取 NEO4J_HOST 或 localhost')
    parser.add_argument('--paper-neo4j-port', type=str, default='',
                        help='Neo4j 端口，默认读取 NEO4J_PORT 或 7687')
    parser.add_argument('--paper-neo4j-user', type=str, default='',
                        help='Neo4j 用户，默认读取 NEO4J_USER 或 neo4j')
    parser.add_argument('--paper-neo4j-password', type=str, default='',
                        help='Neo4j 密码，默认读取 NEO4J_PASSWORD')
    parser.add_argument('--enable-arxiv-fine-translation', action='store_true',
                        help='启用 Arxiv 论文精细翻译（Docker 插件适配）')
    parser.add_argument('--arxiv-input', type=str, default='',
                        help='Arxiv ID 或 URL，例如 2301.00234')
    parser.add_argument('--arxiv-daas-url', type=str, default=os.getenv('ARXIV_DAAS_URL', ''),
                        help='DaaS 服务 URL，例如 http://localhost:18000/stream')
    parser.add_argument('--arxiv-output-dir', type=str, default='./output/arxiv_fine_translation',
                        help='Arxiv 精细翻译输出目录')
    parser.add_argument('--arxiv-advanced-arg', type=str, default='',
                        help='附加翻译提示词，传递给插件命令')
    parser.add_argument('--arxiv-timeout', type=int, default=1800,
                        help='Arxiv 精细翻译请求超时（秒）')
    parser.add_argument('--arxiv-persist-storage', action='store_true',
                        help='将 Arxiv 精细翻译结果写入 PostgreSQL+Neo4j')

    parser.add_argument('--enable-md-translate', action='store_true',
                        help='启用 Markdown 中英互译插件')
    parser.add_argument('--md-input', type=str, default='',
                        help='翻译输入：本地 .md 文件/目录，或 GitHub URL')
    parser.add_argument('--md-lang', type=str, default='en->zh',
                        help="翻译方向：'en->zh'（默认）/ 'zh->en' / 任意语言名，如 Japanese")
    parser.add_argument('--md-output-dir', type=str, default='./output/md_translate',
                        help='Markdown 翻译输出目录')
    parser.add_argument('--md-additional-prompt', type=str, default='',
                        help='附加翻译指令，追加到系统提示词')
    parser.add_argument('--md-max-workers', type=int, default=1,
                        help='并行翻译片段线程数（本地 LLM 建议保持 1）')
    parser.add_argument('--md-no-llm', action='store_true',
                        help='跳过 LLM 调用，原样输出（用于调试）')
    parser.add_argument('--md-persist-storage', action='store_true',
                        help='将翻译结果写入 PostgreSQL+Neo4j')

    parser.add_argument('--enable-pdf-translation', action='store_true',
                        help='启用 PDF 论文全文翻译（提取标题&摘要+多线程翻译全文）')
    parser.add_argument('--pdf-input', type=str, default='',
                        help='PDF 文件路径')
    parser.add_argument('--pdf-target-lang', type=str, default='Chinese',
                        help='翻译目标语言（默认 Chinese）')
    parser.add_argument('--pdf-output-dir', type=str, default='./output/pdf_translation',
                        help='PDF 翻译输出目录')
    parser.add_argument('--pdf-additional-prompt', type=str, default='',
                        help='附加翻译指令，追加到系统提示词')
    parser.add_argument('--pdf-max-tokens-per-fragment', type=int, default=1024,
                        help='每个翻译片段最大 Token 数')
    parser.add_argument('--pdf-max-workers', type=int, default=3,
                        help='并行翻译片段线程数')
    parser.add_argument('--pdf-no-llm', action='store_true',
                        help='跳过 LLM 调用，原样输出（用于调试）')
    parser.add_argument('--pdf-persist-storage', action='store_true',
                        help='将翻译结果写入 PostgreSQL+Neo4j')

    parser.add_argument('--enable-arxiv-helper', action='store_true',
                        help='启用 Arxiv 快速助手（下载 PDF + 翻译摘要）')
    parser.add_argument('--arxiv-helper-url', type=str, default='',
                        help='Arxiv 论文 URL 或 ID（如 2301.00234 或 https://arxiv.org/abs/2301.00234）')
    parser.add_argument('--arxiv-helper-dir', type=str, default='./output/arxiv_quick_helper',
                        help='PDF 下载输出目录')
    parser.add_argument('--arxiv-helper-lang', type=str, default='Chinese',
                        help='摘要翻译目标语言（默认 Chinese）')
    parser.add_argument('--arxiv-helper-no-translation', action='store_true',
                        help='跳过摘要翻译，仅下载 PDF 和获取元信息')
    parser.add_argument('--arxiv-helper-persist-storage', action='store_true',
                        help='将处理结果写入 PostgreSQL+Neo4j')

    parser.add_argument('--enable-scholar-helper', action='store_true',
                        help='启用谷歌学术统合小助手（输入 Scholar 搜索页 URL 生成 related works）')
    parser.add_argument('--scholar-url', type=str, default='',
                        help='Google Scholar 搜索页 URL')
    parser.add_argument('--scholar-output-dir', type=str, default='./output/google_scholar_helper',
                        help='Google Scholar helper 输出目录')
    parser.add_argument('--scholar-topic-hint', type=str, default='',
                        help='related works 主题提示（可选）')
    parser.add_argument('--scholar-target-lang', type=str, default='Chinese',
                        help='related works 输出语言（默认 Chinese）')
    parser.add_argument('--scholar-max-papers', type=int, default=20,
                        help='最多解析的 Scholar 条目数（默认 20）')
    parser.add_argument('--scholar-no-llm', action='store_true',
                        help='跳过 LLM 生成，输出 fallback 相关工作草稿')
    parser.add_argument('--scholar-additional-prompt', type=str, default='',
                        help='附加 related works 写作指令')
    parser.add_argument('--scholar-persist-storage', action='store_true',
                        help='将 Scholar helper 结果写入 PostgreSQL+Neo4j')

    return parser
