"""Worst-case prompt measurement for budget calibration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.infra.token_budget_policy import (
    apply_token_budget_to_prompt,
    estimate_text_tokens,
)

# --- graph_reasoning WORST CASE ---
gap_detail = "\n".join(
    f"{i}. [HIGH] mechanism_gap: \u836f\u6750{i} (herb) \u2014 "
    f"\u7f3a\u5c11\u836f\u6750{i}\u5bf9\u813e\u6c14\u865a\u8bc1\u7684\u4f5c\u7528\u673a\u5236\uff0c"
    f"\u56fe\u8c31\u4e2d\u65e0\u76f4\u63a5\u901a\u8def"
    for i in range(1, 11)
)
kg_summary = "\n".join([
    "\u56fe\u8c31\u8282\u70b9\u6570: 5000\uff0c\u8fb9\u6570: 12000",
    "\u300c\u9ec4\u82aa\u300d\u90bb\u57df: 25 \u4e2a\u90bb\u5c45 "
    "(\u8865\u4e2d\u76ca\u6c14\u6c64, \u813e\u6c14\u865a\u8bc1, \u9ec4\u82aa\u591a\u7cd6, "
    "\u5347\u9633\u4e3e\u9677, \u8865\u80ba\u56fa\u8868, \u751f\u8109\u996e, "
    "\u5f53\u5f52\u8865\u8840\u6c64, \u9632\u5df1\u9ec4\u82aa\u6c64)",
    "\u300c\u5f53\u5f52\u300d\u90bb\u57df: 18 \u4e2a\u90bb\u5c45 "
    "(\u56db\u7269\u6c64, \u8865\u8840\u6d3b\u8840, \u963f\u9b4f\u9178, "
    "\u8840\u865a\u8bc1, \u5987\u79d1, \u5f53\u5f52\u8865\u8840\u6c64, "
    "\u516b\u73cd\u6c64, \u5341\u5168\u5927\u8865\u6c64)",
    "\u300c\u767d\u672f\u300d\u90bb\u57df: 15 \u4e2a\u90bb\u5c45 "
    "(\u56db\u541b\u5b50\u6c64, \u53c2\u82d3\u767d\u672f\u6563, "
    "\u5065\u813e\u71e5\u6e7f, \u82cd\u672f\u916e, \u813e\u865a\u6cc4\u6cfb, "
    "\u75f0\u996e, \u4e94\u82d3\u6563, \u7406\u4e2d\u6c64)",
    "\u300c\u4eba\u53c2\u300d\u90bb\u57df: 22 \u4e2a\u90bb\u5c45 "
    "(\u56db\u541b\u5b50\u6c64, \u5927\u8865\u5143\u714e, \u72ec\u53c2\u6c64, "
    "\u751f\u8109\u996e, \u4eba\u53c2\u7682\u82f7Rg1, \u6c14\u865a\u8bc1, "
    "\u5143\u6c14\u4e8f\u635f)",
    "\u8def\u5f84: \u9ec4\u82aa \u2192 \u8865\u6c14 \u2192 \u813e \u2192 "
    "\u5065\u813e \u2192 \u767d\u672f",
    "\u8def\u5f84: \u4eba\u53c2 \u2192 \u5927\u8865\u5143\u6c14 \u2192 \u5fc3 "
    "\u2192 \u517b\u5fc3 \u2192 \u5f53\u5f52",
    "\u8def\u5f84: \u67f4\u80e1 \u2192 \u758f\u809d \u2192 \u809d \u2192 "
    "\u85cf\u8840 \u2192 \u5f53\u5f52",
])
ctx = (
    "\u7814\u7a76\u4e3b\u9898\uff1a\u8865\u4e2d\u76ca\u6c14\u6c64\u591a\u9776\u70b9"
    "\u4f5c\u7528\u673a\u5236\u3002\u5df2\u6709\u6587\u732e30\u4f59\u7bc7\u3002"
    "\u5b9e\u9a8c\u8868\u660e\u9ec4\u82aa\u591a\u7cd6\u901a\u8fc7TLR4/NF-\u03baB\u901a\u8def"
    "\u8c03\u8282\u514d\u75ab\u529f\u80fd\u3002"
    "\u4f46\u6574\u65b9\u5c42\u9762\u7f3a\u4e4f\u7cfb\u7edf\u6027\u7814\u7a76\u3002"
    "\u9700\u8981\u63a2\u7d22\u65b9\u4e2d\u5404\u5473\u836f\u7684\u534f\u540c\u6548\u5e94"
    "\u4e0e\u4e3b\u8981\u901a\u8def\u3002"
)
kg_user = (
    "\u4f60\u662f\u4e2d\u533b\u79d1\u7814\u5047\u8bbe\u751f\u6210\u4e13\u5bb6\u3002"
    "\u8bf7\u57fa\u4e8e\u4ee5\u4e0b\u77e5\u8bc6\u56fe\u8c31\u7f3a\u53e3\u5206\u6790"
    "\u751f\u6210\u9ad8\u8d28\u91cf\u7814\u7a76\u5047\u8bbe\u3002\n\n"
    "## \u77e5\u8bc6\u56fe\u8c31\u7f3a\u53e3\u5206\u6790\n\n"
    f"\u5171\u53d1\u73b0 10 \u4e2a\u77e5\u8bc6\u7f3a\u53e3\uff1a\n{gap_detail}\n\n"
    "## \u56fe\u8c31\u7ed3\u6784\u6458\u8981\n\n"
    f"{kg_summary}\n\n"
    "## \u7814\u7a76\u4e0a\u4e0b\u6587\n\n"
    f"{ctx}\n\n"
    "## \u8981\u6c42\n\n"
    "\u8bf7\u57fa\u4e8e\u4e0a\u8ff0\u56fe\u8c31\u7f3a\u53e3\u548c\u7ed3\u6784\u4fe1\u606f"
    "\uff0c\u751f\u6210 5 \u6761\u53ef\u9a8c\u8bc1\u7684\u4e2d\u533b\u79d1\u7814\u5047\u8bbe\u3002"
)
schema = (
    "\u8bf7\u4e25\u683c\u6309\u4ee5\u4e0b JSON Schema \u8f93\u51fa\uff0c"
    "\u53ea\u8f93\u51fa\u5355\u4e2a JSON \u6570\u7ec4\uff0c\u7981\u6b62\u9644\u52a0\u89e3\u91ca\u3002"
    "\n\nJSON Schema:\n"
    '{"type":"array","minItems":1,"items":{"type":"object",'
    '"required":["title","statement","rationale","novelty","feasibility",'
    '"evidence_support","validation_plan","keywords"],'
    '"properties":{"title":{"type":"string"},"statement":{"type":"string"},'
    '"rationale":{"type":"string"},"novelty":{"type":"number"},'
    '"feasibility":{"type":"number"},"evidence_support":{"type":"number"},'
    '"validation_plan":{"type":"string"},'
    '"keywords":{"type":"array","items":{"type":"string"}}}}}'
)
kg_sys = (
    "\u4f60\u662f\u4e2d\u533b\u79d1\u7814\u5047\u8bbe\u751f\u6210\u4e13\u5bb6\u3002"
    "\u8bf7\u57fa\u4e8e\u77e5\u8bc6\u56fe\u8c31\u7f3a\u53e3\u5206\u6790\u4e0e\u7ed3\u6784"
    "\u8bc1\u636e\u751f\u6210\u9ad8\u8d28\u91cf\u7814\u7a76\u5047\u8bbe\u3002"
)

tok_kg = (estimate_text_tokens(kg_user) + estimate_text_tokens(kg_sys)
          + estimate_text_tokens(schema))
print(f"graph_reasoning WORST (10 gaps, large subgraph): {tok_kg} tokens")
r4 = apply_token_budget_to_prompt(
    kg_user, system_prompt=kg_sys, task="graph_reasoning",
    purpose="default", suffix_prompt=schema,
)
print(f"  After budget: trimmed={r4.trimmed}, "
      f"after={r4.total_input_tokens_after}, before={r4.total_input_tokens_before}")
if r4.trimmed:
    pct = 100 * (1 - r4.user_tokens_after / max(1, r4.user_tokens_before))
    print(f"  Info loss: ~{pct:.0f}%")

print()
print("=" * 60)
print("FULL SUMMARY")
print("=" * 60)
print(f"  {'Task':<30} {'Typical':>8} {'Worst':>8} {'Budget':>8}")
print(f"  {'-'*30} {'-'*8} {'-'*8} {'-'*8}")
print(f"  {'graph_reasoning':<30} {'773':>8} {tok_kg:>8} {'1152':>8}")
print(f"  {'paper_full_section':<30} {'1080':>8} {'4543':>8} {'1792':>8}")
print(f"  {'large_evidence_synthesis':<30} {'336':>8} {'2814':>8} {'1400':>8}")
print()
print("ANALYSIS:")
print("  graph_reasoning: typical OK, worst case may slightly exceed budget")
print("  paper_full_section: WORST CASE ~4500 tok CN >> 1792 budget (NEEDS TRIM)")
print("  large_evidence_synthesis: WORST CASE ~2800 tok >> 1400 budget (NEEDS TRIM)")
print()
print("KEY INSIGHT: paper_full_section and large_evidence_synthesis are")
print("CAUTIOUS/UNSUITABLE tasks. Trimming is INTENTIONAL for 7B stability.")
print("The budget should allow typical prompts through but deliberately")
print("trim worst-case overflows to keep the 7B model in its stable zone.")
