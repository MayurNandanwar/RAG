import os
import hashlib
import bcrypt
import jwt
from fastapi.security import  HTTPAuthorizationCredentials, HTTPBearer
from fastapi import HTTPException,Depends
from datetime import datetime,timezone, timedelta
from fastapi import Request,Response
from slowapi.util import get_remote_address
from dotenv import load_dotenv


load_dotenv()
security = HTTPBearer()

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "5")
)

REFRESH_TOKEN_EXPIRE_DAYS = int(
    os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")
)

REFRESH_COOKIE_NAME = "refresh_token"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

def get_user_id(request: Request):
    authorization = request.headers.get("Authorization")

    if not authorization:
        return get_remote_address(request)

    try:
        scheme, token = authorization.split(" ", 1)

        if scheme.lower() != "bearer":
            return get_remote_address(request)

        # Use the SAME JWT decoding logic that your verify_access_token uses
        token_data = decode_token(token)
        user_id = token_data["sub"]
        return str(user_id)

    except Exception:
        return get_remote_address(request)




def _bcrypt_secret(secret: str) -> bytes:
    secret_bytes = secret.encode("utf-8")
    # bcrypt only accepts 72 bytes; shrink longer values first
    if len(secret_bytes) > 72:
        secret_bytes = hashlib.sha256(secret_bytes).digest()
    return secret_bytes


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(_bcrypt_secret(password), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(_bcrypt_secret(password), hashed.encode("utf-8"))


def create_access_token(user_id: str, secret_key, algorithm="HS256") -> str:

    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }

    return jwt.encode(payload, secret_key, algorithm=algorithm)


def create_refresh_token(user_id: str, secret_key, algorithm="HS256") -> str:

    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }

    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

    except jwt.ExpiredSignatureError:

        raise HTTPException(
            status_code=401,
            detail="Token expired"
        )

    except jwt.InvalidTokenError:

        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )


def verify_access_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Access token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid access token")
    
