"""Survey research output files."""
import glob
import json
import os
from pathlib import Path

imrd_md = glob.glob("output/cycle_*_imrd_report.md")
imrd_docx = glob.glob("output/cycle_*_imrd_report.docx")
sessions = glob.glob("output/research_session_*.json")
demo = glob.glob("output/cycle_demo_results_*.json")

print(f"IMRD reports (md): {len(imrd_md)}")
print(f"IMRD reports (docx): {len(imrd_docx)}")
print(f"Research sessions: {len(sessions)}")
print(f"Cycle demo results: {len(demo)}")

# Sample session
if sessions:
    latest = sorted(sessions, key=os.path.getmtime, reverse=True)[0]
    print(f"\nLatest session: {latest}")
    with open(latest, encoding="utf-8") as f:
        d = json.load(f)
    print(f"Keys: {list(d.keys())}")
    for k in ["cycle_id", "cycle_name", "status", "current_phase", "research_objective"]:
        val = d.get(k, "N/A")
        print(f"  {k}: {val}")
    # phases
    phases = d.get("phase_results") or d.get("phases") or {}
    if isinstance(phases, dict):
        print(f"  phases: {list(phases.keys())}")

# Sample IMRD
if imrd_md:
    latest_imrd = sorted(imrd_md, key=os.path.getmtime, reverse=True)[0]
    print(f"\nLatest IMRD: {latest_imrd}")
    with open(latest_imrd, encoding="utf-8") as f:
        lines = f.readlines()
    title = lines[0].strip() if lines else "?"
    print(f"Lines: {len(lines)}, Title: {title}")

# web_console_jobs
jobs = glob.glob("output/web_console_jobs/*.json")
print(f"\nWeb console jobs: {len(jobs)}")
if jobs:
    for j in sorted(jobs, key=os.path.getmtime, reverse=True)[:3]:
        with open(j, encoding="utf-8") as f:
            jd = json.load(f)
        print(f"  {Path(j).name}: status={jd.get('status')}, topic={jd.get('topic','?')[:40]}")
