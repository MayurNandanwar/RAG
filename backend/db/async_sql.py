import asyncpg
from datetime import datetime


DATABASE_URL = 'postgresql://postgres:postgres@localhost:5432/langgraph_db'


pool = None


async def init_db():
    global pool

    pool = await asyncpg.create_pool(DATABASE_URL,
                                     min_size=5,
                                     max_size=20)

async def close_db():
    global pool

    if pool:
        await pool.close()
        pool = None




async def get_request(approval_id: str):

    async with pool.acquire() as conn:

        row = await conn.fetchrow("""
                SELECT approval_id, user_id, query, status
                FROM approval_requests
                WHERE approval_id = $1
                """,
                approval_id
            )
        

        if row is None:
            return None

        return {
            "approval_id": row[0],
            "user_id": row[1],
            "query": row[2],
            "status": row[3]
        }

async def update_status(approval_id: str, status: str):

    async with pool.acquire() as conn:

        await conn.execute(
            """
            UPDATE approval_requests
            SET
                status = $1,
                updated_at = $2
            WHERE approval_id = $3
            """,
            status,
            datetime.now(),
            approval_id,
        )

async def save_request(
    approval_id: str,
    user_id: str,
    query: str,
    status: str = "PENDING"
):

    async with pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO approval_requests
            (approval_id, user_id, query, status,created_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            approval_id,
            user_id,
            query,
            status,
            datetime.now(),
        )


async def save_chat_message(user_id, approval_id, role, message):

    async with pool.acquire() as conn:

        await conn.execute(
            """
            INSERT INTO chat_messages
            (user_id, approval_id, role, message)
            VALUES ($1, $2, $3, $4)
            """,
            user_id,
            approval_id,
            role,
            message,
        )
