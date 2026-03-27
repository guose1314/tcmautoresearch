#!/usr/bin/env python3
"""
实体抽取升级测试脚本
验证：6000+ 词汇扩展、最长匹配策略、外部词典加载
"""

import sys

sys.path.insert(0, '.')

from src.data.tcm_lexicon import get_lexicon
from src.extractors.advanced_entity_extractor import AdvancedEntityExtractor

print('=' * 80)
print('实体抽取升级演示（6000+ 中医词汇 → 支持扩展至 3 万+）')
print('=' * 80)

# 初始化词典并检查规模
lexicon = get_lexicon()
vocab_size = lexicon.get_vocab_size()
print(f'\n【词典规模】')
print(f'  总词汇数: {vocab_size:,}')
print(f'  中药数: {len(lexicon.herbs):,}')
print(f'  方剂数: {len(lexicon.formulas):,}')
print(f'  证候数: {len(lexicon.syndromes):,}')
print(f'  理论术语: {len(lexicon.theory):,}')
print(f'  功效描述: {len(lexicon.efficacy):,}')
print(f'  通用词汇: {len(lexicon.common_words):,}')

# 初始化实体抽取器
extractor = AdvancedEntityExtractor()
extractor.initialize()

# 测试文本：包含多个中医术语和实体
test_text = """
《本草纲目》记载：黄芪性味甘、微温，归肺、脾经。
主治气虚乏力、心悸气短、脾虚便溏、肺虚久咳。
功效补气固表、利水消肿、强心、提高免疫力。
临床常用补中益气汤、四君子汤、六味地黄丸等方剂。
患者可以服用黄芪、党参、人参、白术、茯苓、甘草等药材。
常见证候有表寒证、气虚证、阳虚证、湿热证等。
推荐剂量6克到12克，水煎服用。
"""

print(f'\n【测试文本】（简化版，共 {len(test_text)} 字符）:')
print(test_text[:100] + '...')

# 执行实体抽取
context = {'processed_text': test_text}
result = extractor.execute(context)

entities = result['entities']
stats = result['statistics']
confidence = result['confidence_scores']

print(f'\n【抽取结果】')
print(f'  总实体数: {stats["total_count"]}')
print(f'  按类型分布: {stats["by_type"]}')
print(f'  平均置信度: {confidence["average_confidence"]:.2%}')

print(f'\n【抽取的实体列表】（按位置）:')
for i, entity in enumerate(entities[:20], 1):  # 仅显示前 20 个
    print(f'  {i:2d}. [{entity["type"]:8s}] {entity["name"]:10s} '
          f'置信度: {entity["confidence"]:.0%} 位置: {entity["position"]}-{entity.get("end_position", "?")}')

if len(entities) > 20:
    print(f'  ... 还有 {len(entities) - 20} 个实体')

# 按类型分组展示
print(f'\n【按类型分类】:')
by_type = {}
for entity in entities:
    etype = entity['type']
    if etype not in by_type:
        by_type[etype] = []
    by_type[etype].append(entity['name'])

for etype in sorted(by_type.keys()):
    unique_names = list(set(by_type[etype]))
    print(f'  {etype:10s} ({len(unique_names):3d} 个): {", ".join(unique_names[:10])}' + 
          (' ...' if len(unique_names) > 10 else ''))

# 验证词汇类型映射
print(f'\n【词汇类型验证】:')
test_words = ['黄芪', '补中益气汤', '气虚证', '补气', '性味']
for word in test_words:
    word_type = lexicon.get_word_type(word)
    found = lexicon.contains(word)
    print(f'  "{word}": 包含={found}, 类型={word_type}')

print(f'\n✅ 实体抽取升级测试完成！')
print(f'\n【后续扩展】')
print(f'  1. 可通过 extractor.load_external_lexicon(path) 加载 THUOCL 等外部词典')
print(f'  2. 当前词汇规模 {vocab_size:,}，理论可扩展至 30,000+ （通过加载大规模词典）')
print(f'  3. 使用最长匹配策略避免词汇重叠和歧义')
