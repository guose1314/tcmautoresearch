import sqlite3
import os

db_path = r'C:\Users\hgk\tcmautoresearch\data\test\tcmautoresearch.db'
if not os.path.exists(db_path):
    print(f'Database not found at {db_path}')
    exit(0)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
try:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print('Tables:', tables)
    for table in tables:
        table_name = table[0]
        cursor.execute(f"SELECT count(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f'Table {table_name}: {count} rows')
        
    cursor.execute("SELECT observe_philology FROM research_sessions WHERE cycle_id='cycle-1'")
    row = cursor.fetchone()
    if row:
        print('Observe Philology length:', len(row[0]) if row[0] else 'None')
        # print first 200 chars
        if row[0]:
            print('Observe Philology preview:', row[0][:200])
except Exception as e:
    print('Error:', e)
conn.close()
