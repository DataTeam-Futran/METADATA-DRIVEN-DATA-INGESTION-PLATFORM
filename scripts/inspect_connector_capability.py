from app.db.metastore import get_metastore_connection

with get_metastore_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'conn'
              AND table_name = 'connector_version_capability'
            ORDER BY ordinal_position;
        """)

        for row in cur.fetchall():
            print(row)