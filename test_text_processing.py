#!/usr/bin/env python3
"""
文本处理升级测试脚本
验证：繁简转换 + jieba 分词 + 古文断句补全
"""

import sys

sys.path.insert(0, '.')

from src.preprocessor.document_preprocessor import DocumentPreprocessor

print('=' * 70)
print('中医古籍文本预处理演示（繁简转换 + jieba 分词 + 古文断句）')
print('=' * 70)

# 模拟现代古籍文本（繁体、换行混乱）
ancient_corpus = """《本草綱目》云：黃芪性味甘
微溫。歸肺、脾經


主治氣虛乏力；心悸氣短；自汗盜汗；脾虛便溏；久瀉脫肛；肺衛虛弱，容易感冒；
瘡瘍不易癒合。
功效：補中益氣，健脾益胃；增強體質，提高免疫力；利水消腫，強心作用。
劑量6克到12克為常用。"""

# 初始化
config = {'convert_mode': 't2s', 'user_dict_path': None}
preprocessor = DocumentPreprocessor(config)
preprocessor.initialize()

# 预处理
context = {'raw_text': ancient_corpus}
result = preprocessor.execute(context)

print('\n【原始文本】（繁体、换行混乱）:')
print(repr(ancient_corpus[:100]))

print('\n【处理后的文本】（简体、标准化）:')
print(result['processed_text'][:150])

print('\n【处理步骤】:')
for step in result['processing_steps']:
    print(f'  ✓ {step}')

print('\n【元数据统计】:')
metadata = result['metadata']
print(f'  整体文件大小: {metadata["file_size"]} 字符')
print(f'  分词后词汇数: {metadata.get("token_count", "N/A")}')
print(f'  繁简转换模式: {metadata.get("convert_mode", "N/A")}')
print(f'  编码检测: {metadata["encoding_detected"]}')

# 古文分词测试
print('\n【古文分词 + 断句补全演示】:')
ancient_text = '黄芪主治气虚乏力。心悸气短。自汗盗汗。'
print(f'  输入: {ancient_text}')
sentence_segs = preprocessor.segment_with_ancient_punctuation(ancient_text)
for seg_idx, seg in enumerate(sentence_segs):
    if seg:
        print(f'  句子 {seg_idx + 1}: {" / ".join(seg)}')

# 单独分词测试
print('\n【jieba 分词测试】:')
test_phrase = '黄芪补气固表，利水消肿，强心作用。'
words = preprocessor.segment_text(test_phrase)
print(f'  输入: {test_phrase}')
print(f'  分词: {" / ".join(words)}')

print('\n✅ 所有测试完成！')
