"""Check dashboard data values."""
import re

import requests

s = requests.Session()
r = s.post("http://127.0.0.1:18888/api/auth/login", json={"username": "hgk1988", "password": "Hgk1989225"})
h = {"Authorization": "Bearer " + r.json()["access_token"]}

# Stats
r = s.get("http://127.0.0.1:18888/api/dashboard/stats", headers=h)
cards = re.findall(r'uppercase tracking-wide">(.*?)</p>\s*<p class="text-2xl font-bold.*?">(.*?)</p>', r.text)
print("=== Dashboard Stats ===")
for label, value in cards:
    print(f"  {label}: {value}")

# Workflow
r = s.get("http://127.0.0.1:18888/api/dashboard/research-workflow", headers=h)
print("\n=== Research Workflow ===")
stats = re.findall(r'text-gray-500">(.*?)</span><span class="font-medium.*?">(.*?)</span>', r.text)
for label, value in stats:
    print(f"  {label}: {value}")

# Quality
r = s.get("http://127.0.0.1:18888/api/dashboard/quality", headers=h)
print("\n=== Quality Score ===")
score = re.findall(r'font-bold.*?">(.*?)</span>', r.text)
if score:
    print(f"  Overall Score: {score[0]}")
metrics = re.findall(r'(知识实体覆盖|知识关系密度|论文产出|研究课题完成).*?font-medium">(.*?)</span>', r.text)
for label, value in metrics:
    print(f"  {label}: {value}")

# Recent projects
r = s.get("http://127.0.0.1:18888/api/projects/recent", headers=h)
print("\n=== Recent Projects ===")
titles = re.findall(r'font-medium text-gray-800 truncate">(.*?)(?:<span|</p>)', r.text)
for t in titles[:5]:
    print(f"  - {t.strip()[:70]}")
print(f"  Total items shown: {len(titles)}")
