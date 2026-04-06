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
for kw in ["鍙ょ睄鏂囩尞", "鐮旂┒璇鹃", "宸茬敓鎴愯鏂?, "鐭ヨ瘑瀹炰綋", "KG 鑺傜偣", "IMRD", "鍏ㄩ儴杈撳嚭"]:
    found = kw in html
    print(f"   {'OK' if found else 'MISS'} {kw}")

# 2. Research workflow
r = s.get(f"{BASE}/api/dashboard/research-workflow", headers=h)
print(f"\n2. /api/dashboard/research-workflow: {r.status_code}")
html = r.text
for kw in ["绉戠爺璁烘枃涔﹀啓娴佺▼", "鏂囩尞瑙傚療", "鍋囪鐢熸垚", "瀹為獙楠岃瘉", "鏁版嵁鍒嗘瀽", "璁烘枃鐢熸垚", "鍙嶆€濇€荤粨", "鏈€杩戠敓鎴愯鏂?, "娴佺▼缁熻"]:
    found = kw in html
    print(f"   {'OK' if found else 'MISS'} {kw}")

# 3. Quality
r = s.get(f"{BASE}/api/dashboard/quality", headers=h)
print(f"\n3. /api/dashboard/quality: {r.status_code}")
html = r.text
for kw in ["鐭ヨ瘑瀹炰綋瑕嗙洊", "鐭ヨ瘑鍏崇郴瀵嗗害", "璁烘枃浜у嚭", "鍔ㄦ€佽瘎浼?]:
    found = kw in html
    print(f"   {'OK' if found else 'MISS'} {kw}")

# 4. Recent projects
r = s.get(f"{BASE}/api/projects/recent", headers=h)
print(f"\n4. /api/projects/recent: {r.status_code}")
html = r.text
# Should show real session data
has_content = "hover:bg-gray-50" in html or "鏆傛棤鐮旂┒璁板綍" in html
print(f"   {'OK' if has_content else 'MISS'} has content")

# 5. Projects page
r = s.get(f"{BASE}/api/projects", headers=h)
print(f"\n5. /api/projects: {r.status_code}")
html = r.text
for kw in ["绉戠爺椤圭洰", "鐮旂┒璇鹃", "宸插畬鎴?, "璁烘枃杈撳嚭"]:
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
