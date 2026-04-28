import json
import re
import os

def audit_lexicon(filepath):
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found.")
        return

    categories = {}
    noise_patterns = {
        "PREFIX_NOISE": {
            "prefixes": ["加", "各", "每", "如", "并", "或", "若", "用", "以", "再", "另", "将", "兼"],
            "matches": []
        },
        "DOSAGE_PREFIX": {
            "numerals": "一二三四五六七八九十百千万",
            "units": "钱克两分斤升毫枚颗粒锭丸",
            "matches": []
        },
        "PUNCTUATION_WHITESPACE": {
            "pattern": r"[，。、；：！？,.;:?!（）()「」\"\s]",
            "matches": []
        },
        "LENGTH_ONE": {
            "whitelist": ["桂", "姜", "枣", "参", "术"],
            "matches": []
        },
        "GENERIC_TERMS": {
            "terms": ["小儿", "妇人", "男子", "病人", "共享", "服药", "上述", "诸药", "以上", "病者"],
            "matches": []
        }
    }

    herb_length_4plus = []
    herb_length_6plus = []
    total_noise_count = 0

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                term = data.get("term", "").strip()
                category = data.get("category", "unknown")
                
                categories[category] = categories.get(category, 0) + 1
                
                is_noise = False
                
                # Prefix Noise
                if any(term.startswith(p) for p in noise_patterns["PREFIX_NOISE"]["prefixes"]):
                    noise_patterns["PREFIX_NOISE"]["matches"].append(f"{term} ({category})")
                    is_noise = True
                
                # Dosage Prefix
                if len(term) >= 2 and term[0] in noise_patterns["DOSAGE_PREFIX"]["numerals"] and any(u in term[1:] for u in noise_patterns["DOSAGE_PREFIX"]["units"]):
                     # Simplified dosage check: start with numeral and contains units
                     noise_patterns["DOSAGE_PREFIX"]["matches"].append(f"{term} ({category})")
                     is_noise = True

                # Punctuation/Whitespace
                if re.search(noise_patterns["PUNCTUATION_WHITESPACE"]["pattern"], term):
                    noise_patterns["PUNCTUATION_WHITESPACE"]["matches"].append(f"{term} ({category})")
                    is_noise = True

                # Length One
                if len(term) == 1 and term not in noise_patterns["LENGTH_ONE"]["whitelist"]:
                    noise_patterns["LENGTH_ONE"]["matches"].append(f"{term} ({category})")
                    is_noise = True

                # Generic Terms
                if any(gt in term for gt in noise_patterns["GENERIC_TERMS"]["terms"]):
                    noise_patterns["GENERIC_TERMS"]["matches"].append(f"{term} ({category})")
                    is_noise = True

                if category == "herb":
                    if len(term) > 6:
                        herb_length_6plus.append(term)
                    elif len(term) > 4:
                        herb_length_4plus.append(term)
                
                if is_noise:
                    total_noise_count += 1

            except json.JSONDecodeError:
                continue

    print("=== Total terms by category ===")
    for cat, count in categories.items():
        print(f"{cat}: {count}")
    print()

    for key, data in noise_patterns.items():
        count = len(data["matches"])
        print(f"=== [{key}] (count={count}) ===")
        for m in data["matches"]:
            print(f"  {m}")
        print()

    print(f"=== [HERB_LENGTH > 4] (count={len(herb_length_4plus)}) ===")
    for h in herb_length_4plus:
        print(f"  {h}")
    print()

    print(f"=== [HERB_LENGTH > 6] (count={len(herb_length_6plus)}) ===")
    for h in herb_length_6plus:
        print(f"  {h}")
    print()

    print(f"Total noise items detected: {total_noise_count}")

if __name__ == '__main__':
    audit_lexicon('data/tcm_lexicon.jsonl')
