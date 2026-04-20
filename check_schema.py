import sqlite3
conn = sqlite3.connect(r'C:\Users\hgk\tcmautoresearch\data\test\tcmautoresearch.db')
cursor = conn.cursor()
cursor.execute('PRAGMA table_info(research_sessions)')
columns = cursor.fetchall()
for col in columns:
    print(col)
conn.close()
