import psycopg2
from  datetime import datetime



conn = psycopg2.connect(
    host="localhost",
    database="langgraph_db",
    user="postgres",
    password="postgres"
)

def get_request(approval_id: str):
    cur = conn.cursor()

    cur.execute(
        """
        SELECT approval_id, user_id, query, status
        FROM approval_requests
        WHERE approval_id = %s
        """,
        (approval_id,)
    )

    row = cur.fetchone()

    cur.close()

    if row is None:
        return None

    return {
        "approval_id": row[0],
        "user_id": row[1],
        "query": row[2],
        "status": row[3]
    }

def update_status(approval_id: str, status: str):

    cur = conn.cursor()

    cur.execute(
    """
    UPDATE approval_requests
    SET
        status = %s,
        updated_at = %s
    WHERE approval_id = %s
    """,
    (
        status,
        datetime.now(),
        approval_id
    )
)
    conn.commit()
    cur.close()




def save_request(
    approval_id: str,
    user_id: str,
    query: str,
    status: str = "PENDING"
):

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO approval_requests
            (approval_id, user_id, query, status,created_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                approval_id,
                user_id,
                query,
                status,
                datetime.now()
            )
        )

    conn.commit()



def save_chat_message(user_id, approval_id, role, message):

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_messages
            (user_id, approval_id, role, message)
            VALUES (%s, %s, %s, %s)
            """,
            (
                user_id,
                approval_id,
                role,
                message
            )
        )

    conn.commit()