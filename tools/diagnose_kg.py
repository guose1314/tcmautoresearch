# -*- coding: utf-8 -*-
import sqlite3
import json
import os
import random
from collections import Counter

DB_PATH = "data/knowledge_graph.db"
PROGRESS_PATH = "logs/batch_distill_progress.jsonl"
LEXICON_PATH = "data/tcm_lexicon.jsonl"
SYNONYMS_PATH = "data/tcm_synonyms.jsonl"

def diagnose_db():
    print("=== 1. Knowledge Graph (SQLite) Diagnostics ===")
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Total entities and breakdown
    cursor.execute("SELECT type, COUNT(*) FROM entities GROUP BY type ORDER BY COUNT(*) DESC LIMIT 10")
    entity_counts = cursor.fetchall()
    total_entities = sum(row[1] for row in entity_counts) if entity_counts else 0
    print(f"Total Entities: {total_entities}")
    print("Breakdown by Type (Top 10):")
    for row in entity_counts:
        print(f"  {row[0]}: {row[1]}")

    # Relations count and breakdown
    cursor.execute("SELECT rel_type, COUNT(*) FROM relations GROUP BY rel_type ORDER BY COUNT(*) DESC LIMIT 20")
    rel_counts = cursor.fetchall()
    total_relations = sum(row[1] for row in rel_counts) if rel_counts else 0
    print(f"\nTotal Relations: {total_relations}")
    print("Breakdown by Relation Type (Top 20):")
    for row in rel_counts:
        print(f"  {row[0]}: {row[1]}")

    # Highest connection degree
    print("\nTop 30 Entities by Connection Degree:")
    try:
        cursor.execute("""
            SELECT name, SUM(degree) as total_degree FROM (
                SELECT src as name, COUNT(*) as degree FROM relations GROUP BY src
                UNION ALL
                SELECT dst as name, COUNT(*) as degree FROM relations GROUP BY dst
            ) GROUP BY name ORDER BY total_degree DESC LIMIT 30
        """)
        for row in cursor.fetchall():
            print(f"  {row[0]} ({row[1]})")
    except Exception as e:
        print(f"Error calculating degree: {e}")

    # Name lengths
    print("\nName Length Distribution:")
    cursor.execute("SELECT name FROM entities")
    names = [row[0] for row in cursor.fetchall() if row[0]]
    lengths = Counter()
    for n in names:
        l = len(n)
        if l >= 4:
            lengths['4+'] += 1
        else:
            lengths[str(l)] += 1
    for l in sorted(lengths.keys()):
        print(f"  Length {l}: {lengths[l]}")

    # Longest names
    print("\nTop 20 Longest Entitiy Names:")
    sorted_by_len = sorted(names, key=len, reverse=True)[:20]
    for n in sorted_by_len:
        print(f"  {len(n)} chars: {n}")

    # Punctuation / Hallucinations
    print("\nTop 20 Entities with Punctuation/Whitespace (Likely Hallucinations):")
    punc_chars = "\u3000\uff0c\u3002\u3001\uff1b\uff1a\uff1f\uff01,.;:?!()[]\u300c\u300d\u201c\u201d "
    count = 0
    for n in names:
        if any(c in n for c in punc_chars):
            print(f"  {n}")
            count += 1
            if count >= 20:
                break

    # Sample relations
    print("\nSample 30 Random Relations:")
    try:
        cursor.execute("""
            SELECT src, rel_type, dst
            FROM relations
            ORDER BY RANDOM()
            LIMIT 30
        """)
        for row in cursor.fetchall():
            print(f"  {row[0]} --[{row[1]}]--> {row[2]}")
    except Exception as e:
        print(f"Error sampling relations: {e}")

    conn.close()

def diagnose_progress():
    print("\n=== 2. Batch Distill Progress Diagnostics ===")
    if not os.path.exists(PROGRESS_PATH):
        print(f"Error: {PROGRESS_PATH} not found.")
        return

    entries = []
    with open(PROGRESS_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except:
                continue

    total = len(entries)
    ok_true = [e for e in entries if e.get('ok') is True]
    ok_false = [e for e in entries if e.get('ok') is False]

    print(f"Total entries: {total}")
    print(f"ok=true count: {len(ok_true)}")
    print(f"ok=false count: {len(ok_false)}")

    if ok_true:
        avg_elapsed = sum(e.get('elapsed_s', 0) for e in ok_true) / len(ok_true)
        max_elapsed = max(e.get('elapsed_s', 0) for e in ok_true)
        avg_chars = sum(e.get('chars_sent', 0) for e in ok_true) / len(ok_true)
        print(f"Average elapsed_s: {avg_elapsed:.2f}")
        print(f"Max elapsed_s: {max_elapsed:.2f}")
        print(f"Average chars_sent: {avg_chars:.2f}")

        print("\nTop 10 Largest Succeeded Files (by chars_sent):")
        sorted_large = sorted(ok_true, key=lambda x: x.get('chars_sent', 0), reverse=True)[:10]
        for e in sorted_large:
            print(f"  {e.get('file')}: {e.get('chars_sent')} chars, {e.get('elapsed_s')}s")

    if ok_false:
        print("\nTop 10 Error Message Prefixes:")
        errors = []
        for e in ok_false:
            msg = e.get('error')
            if not msg:
                msg = str(e.get('status_code', 'Unknown error'))
            errors.append(str(msg)[:50])
            
        error_counts = Counter(errors)
        for msg, count in error_counts.most_common(10):
            print(f"  {msg}: {count}")

        print("\nSmall Files (<200KB) that Failed (Top 10):")
        small_fails = [e for e in ok_false if (e.get('chars_sent') is not None and e.get('chars_sent', 0) < 200000) or e.get('chars_sent') is None][:10]
        for e in small_fails:
             print(f"  {e.get('file')}: {e.get('chars_sent')} chars, error: {e.get('error')}")

def diagnose_jsonl(path, title):
    print(f"\n=== {title} ===")
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        return
    
    categories = Counter()
    total = 0
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                cat = data.get('category', 'unknown')
                categories[cat] += 1
                total += 1
            except:
                continue
    
    print(f"Total: {total}")
    for cat, count in categories.items():
        print(f"  {cat}: {count}")

if __name__ == "__main__":
    diagnose_db()
    diagnose_progress()
    diagnose_jsonl(LEXICON_PATH, "3. TCM Lexicon Diagnostics")
    diagnose_jsonl(SYNONYMS_PATH, "4. TCM Synonyms Diagnostics")