"""Fix local method references in observe_phase.py.

Run: python tools/_fix_observe_refs.py
"""
import re

with open('src/research/phases/observe_phase.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix LOCAL self.pipeline._xxx -> self._xxx
local_methods = [
    '_collect_ctext_observation_corpus',
    '_collect_local_observation_corpus',
    '_extract_corpus_text_entries',
    '_should_collect_ctext_corpus',
    '_should_collect_local_corpus',
]

for method in local_methods:
    old = f'self.pipeline.{method}('
    new = f'self.{method}('
    count = content.count(old)
    content = content.replace(old, new)
    print(f'  Replaced {count}x: {old}')

with open('src/research/phases/observe_phase.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('\nRemaining self.pipeline references:')
remaining = re.findall(r'self\.pipeline\.([a-zA-Z_]+)', content)
for r in sorted(set(remaining)):
    count = content.count(f'self.pipeline.{r}')
    print(f'  self.pipeline.{r}: {count}')

# Verify Chinese
chinese_count = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
print(f'\nChinese chars: {chinese_count}')
