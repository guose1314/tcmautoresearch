"""Extract observe phase methods from git history and create observe_phase.py mixin.

Run: python tools/_extract_observe_phase.py
"""
import re
import subprocess
import textwrap

# Get the original monolithic pipeline_phase_handlers.py from git
content = subprocess.check_output(
    ['git', 'show', '476cb71:src/research/pipeline_phase_handlers.py'],
    text=True, encoding='utf-8'
)
lines = content.split('\n')

# Find observe method boundaries (line 96 to 962)
observe_start = None
observe_end = None
for i, line in enumerate(lines):
    if 'def execute_observe_phase' in line and observe_start is None:
        observe_start = i
    if 'def execute_hypothesis_phase' in line:
        observe_end = i
        break

print(f"Observe methods: lines {observe_start+1} to {observe_end}")

# Extract observe methods (they are indented as class methods with 4-space indent)
observe_lines = lines[observe_start:observe_end]

# Build the mixin file
header = '''\
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPipeline

from src.collector.corpus_bundle import (
    CorpusBundle,
    extract_text_entries,
    is_corpus_bundle,
)
from src.knowledge.tcm_knowledge_graph import TCMKnowledgeGraph


class ObservePhaseMixin:
    """Mixin: observe 阶段处理方法。

    由 ResearchPhaseHandlers 通过多重继承组合使用。
    运行时 ``self.pipeline`` 由 ResearchPhaseHandlers.__init__ 设置。
    """

    pipeline: "ResearchPipeline"  # provided by ResearchPhaseHandlers

'''

# The original methods reference self.pipeline (which is the ResearchPhaseHandlers pattern)
# We need to keep self.pipeline references as-is for now
observe_body = '\n'.join(observe_lines)

# Check for any references to self. that need fixing
# In the original, methods like self._should_collect_ctext_corpus were on the same class
# so self.xxx should work directly. But self.pipeline.xxx was used for pipeline access.
# Let's verify
pipeline_refs = [l.strip() for l in observe_lines if 'self.pipeline.' in l]
self_refs = [l.strip() for l in observe_lines if 'self.' in l and 'self.pipeline' not in l and 'self._' in l]

print(f"\nself.pipeline references: {len(pipeline_refs)}")
for r in pipeline_refs[:5]:
    print(f"  {r[:100]}")
print(f"\nself._ (direct) references: {len(self_refs)}")
for r in self_refs[:5]:
    print(f"  {r[:100]}")

# Write the file
output = header + observe_body + '\n'
target = 'src/research/phases/observe_phase.py'
with open(target, 'w', encoding='utf-8') as f:
    f.write(output)

print(f"\nWrote {target}: {len(output)} chars, {output.count(chr(10))+1} lines")

# Verify
with open(target, 'r', encoding='utf-8') as f:
    verify = f.read()
chinese_count = sum(1 for c in verify if '\u4e00' <= c <= '\u9fff')
print(f"Verification: {len(verify)} chars, Chinese chars: {chinese_count}")
