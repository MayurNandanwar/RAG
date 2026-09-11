from pymongo import AsyncMongoClient
import os

MONGO_URL = os.getenv(
    "MONGO_URL",
    "mongodb://127.0.0.1:27017/"
)

client = AsyncMongoClient(
    MONGO_URL,
    serverSelectionTimeoutMS=5000)


db = client["mydb"]

users_collection = db["users"]


async def connect_mongo():
    try:
        await client.admin.command("ping")
        print("MongoDB connected successfully!")
    except Exception as e:
        print(f"MongoDB connection failed: {e}")
        raise


async def close_mongo():
    await client.close()
    print("MongoDB connection closed")
