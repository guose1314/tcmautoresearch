"""Test all dashboard endpoints after overhaul."""
import requests

BASE = "http://127.0.0.1:18888"
s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"username": "hgk1988", "password": "Hgk1989225"})
assert r.status_code == 200, f"Login failed: {r.status_code}"
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}"}

# 1. Dashboard stats
r = s.get(f"{BASE}/api/dashboard/stats", headers=h)
print(f"1. /api/dashboard/stats: {r.status_code}")
html = r.text
for kw in ["古籍文献", "研究课题", "已生成论文", "知识实体", "KG 节点", "IMRD", "全部输出"]:
    found = kw in html
    print(f"   {'OK' if found else 'MISS'} {kw}")

# 2. Research workflow
r = s.get(f"{BASE}/api/dashboard/research-workflow", headers=h)
print(f"\n2. /api/dashboard/research-workflow: {r.status_code}")
html = r.text
for kw in ["科研论文书写流程", "文献观察", "假设生成", "实验验证", "数据分析", "论文生成", "反思总结", "最近生成论文", "流程统计"]:
    found = kw in html
    print(f"   {'OK' if found else 'MISS'} {kw}")

# 3. Quality
r = s.get(f"{BASE}/api/dashboard/quality", headers=h)
print(f"\n3. /api/dashboard/quality: {r.status_code}")
html = r.text
for kw in ["知识实体覆盖", "知识关系密度", "论文产出", "动态评估"]:
    found = kw in html
    print(f"   {'OK' if found else 'MISS'} {kw}")

# 4. Recent projects
r = s.get(f"{BASE}/api/projects/recent", headers=h)
print(f"\n4. /api/projects/recent: {r.status_code}")
html = r.text
# Should show real session data
has_content = "hover:bg-gray-50" in html or "暂无研究记录" in html
print(f"   {'OK' if has_content else 'MISS'} has content")

# 5. Projects page
r = s.get(f"{BASE}/api/projects", headers=h)
print(f"\n5. /api/projects: {r.status_code}")
html = r.text
for kw in ["科研项目", "研究课题", "已完成", "论文输出"]:
    found = kw in html
    print(f"   {'OK' if found else 'MISS'} {kw}")

# 6. Dashboard HTML template
r = s.get(f"{BASE}/dashboard", headers=h)
print(f"\n6. /dashboard template: {r.status_code}")
html = r.text
for kw in ["research-workflow", "workflow-container", "stats-container", "projects-list"]:
    found = kw in html
    print(f"   {'OK' if found else 'MISS'} {kw}")

print("\n=== ALL CHECKS DONE ===")
