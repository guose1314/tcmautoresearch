import psycopg2
from neo4j import GraphDatabase

pg = psycopg2.connect(host='localhost', port=5432, user='postgres',
                      password='Hgk1989225', dbname='tcmautoresearch')
cur = pg.cursor()
for t in ['documents', 'entities', 'entity_relationships',
          'relationship_types', 'phase_executions', 'research_sessions',
          'research_artifacts', 'research_results',
          'research_learning_feedback']:
    cur.execute(f'SELECT count(*) FROM "{t}"')
    print(f"PG.{t:35s} = {cur.fetchone()[0]}")
pg.close()

drv = GraphDatabase.driver('neo4j://localhost:7687', auth=('neo4j', 'Hgk1989225'))
with drv.session(database='neo4j') as s:
    n = s.run('MATCH (n) RETURN count(n) AS c').single()['c']
    e = s.run('MATCH ()-[r]->() RETURN count(r) AS c').single()['c']
    print(f"Neo4j nodes={n}, edges={e}")
    for r in s.run('MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c ORDER BY c DESC'):
        print(f"  Label {r['label']}: {r['c']}")
    for r in s.run('MATCH ()-[r]->() RETURN type(r) AS rt, count(*) AS c ORDER BY c DESC'):
        print(f"  Rel {r['rt']}: {r['c']}")
drv.close()
