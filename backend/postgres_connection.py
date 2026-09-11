import psycopg2


def get_db_connection(config):
    try:
        conn = psycopg2.connect(**config)
        conn.autocommit = True
        print("✅ Connected to PostgreSQL")
        return conn

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        raise

