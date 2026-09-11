from fastapi import FastAPI, HTTPException, Depends, Request, WebSocket, WebSocketDisconnect, Query, Response, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from dotenv import load_dotenv
from db.mongo import connect_mongo, close_mongo, users_collection
from fastapi.concurrency import run_in_threadpool
from db.async_sql import init_db, close_db, get_request, update_status
from schemas.users import RegisterRequest, LoginRequest
import os
from starlette.responses import HTMLResponse
from bson import ObjectId
from datetime import datetime, timezone
from auth.jwt import (
    get_user_id,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_access_token,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import jwt
import uvicorn
from send_email import send_rejection_email, send_answer_to_user
from chat import define_workflow, extract_response, execute_approved_request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager


DB_URI = (
    "postgresql://postgres:postgres@localhost:5432/langgraph"
)


@asynccontextmanager
async def lifespan(app: FastAPI):

    print("Starting application...")

    try:
        # 1. PostgreSQL CRUD connection
        print("Connecting PostgreSQL...")

        await init_db()

        print("PostgreSQL ready")


        # 2. MongoDB connection
        print("Connecting MongoDB...")
        await connect_mongo()
        print("MongoDB ready")


        # 3. LangGraph PostgreSQL
        print("Creating LangGraph checkpointer...")
        async with AsyncPostgresSaver.from_conn_string(DB_URI) as saver:
            await saver.setup()
            app.state.saver = saver
            print("LangGraph checkpointer ready")


            # 4. Create workflow
            print("Creating workflow...")
            app.state.workflow = define_workflow(saver)

            print("Workflow ready")

            # Application is ready

            print(
                "All services connected. "
                "Application is ready."
            )

            yield
            print("Application shutting down...")

    except Exception as e:

        print(
            f"Application startup failed: {e}"
        )

        raise

    finally:
        await close_mongo()
        await close_db()


app = FastAPI(
    lifespan=lifespan
)


load_dotenv()
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "5"))

REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

REFRESH_COOKIE_NAME = "refresh_token"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


# limit the api
limiter = Limiter(key_func=get_user_id)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# middleware
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"])


class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict):
        websocket = self.active_connections.get(user_id)
        if websocket:
            await websocket.send_json(message)


manager = ConnectionManager()
security = HTTPBearer()


@app.post("/register")
async def register(user: RegisterRequest):

    try:
        # Check email
        existing_user = await users_collection.find_one({"email": user.email})

        if existing_user:
            raise HTTPException(status_code=400,
                                detail="Email already registered")

        # Check username
        existing_username = await users_collection.find_one({"username": user.username})

        if existing_username:
            raise HTTPException(status_code=400,
                                detail="Username already exists")

        # Hash password
        hashed_password = await run_in_threadpool(hash_password,user.password)

        now = datetime.now(timezone.utc)

        user_document = {
            "username": user.username,
            "email": user.email,
            "password": hashed_password,
            "created_at": now,
            "updated_at": now,
            "refresh_token": None}

        print('ser_docs:',user_document)
        await users_collection.insert_one(user_document)

        return {"status_code": 201,
                "message": "Successfully registered"}


    except HTTPException:
        raise


    except Exception as e:
        print(f"Registration error: {e}")

        raise HTTPException(status_code=500,
                            detail="Registration failed")


@app.post("/login")
async def login(user: LoginRequest,response: Response):

    try:
        user_doc = await users_collection.find_one({"email": user.email})
        print('user_doc:',user_doc)
        if not user_doc:
            raise HTTPException(status_code=401,
                                detail="Invalid email or password")

        # Verify password
        valid = await run_in_threadpool(verify_password, user.password, user_doc["password"])

        if not valid:
            raise HTTPException(status_code=401,
                                detail="Invalid email or password")

        user_id = str(user_doc["_id"])

        # Create tokens
        access_token = create_access_token(user_id,JWT_SECRET)
        refresh_token = create_refresh_token(user_id,JWT_SECRET)

        # Hash refresh token before storing
        hashed_refresh_token = await run_in_threadpool(hash_password, refresh_token)

        # Store refresh token hash
        await users_collection.update_one(
                                            {"_id": user_doc["_id"]},
                                            {
                                                "$set": {
                                                    "refresh_token": hashed_refresh_token,
                                                    "updated_at": datetime.now(timezone.utc)
                                                }
                                            }
                                        )

        # Send refresh token as HttpOnly cookie
        set_refresh_cookie(response,refresh_token)

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "message": "Login successful"
        }

    except HTTPException:
        raise

    except Exception as e:
        print(f"Login error: {e}")

        raise HTTPException(
            status_code=500,
            detail="Login failed"
        )
    


@app.post("/refresh")
async def refresh(
    request: Request,
    response: Response
):
    # Get refresh token from HttpOnly cookie
    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Refresh token missing"
        )

    try:
        # 1. Verify JWT signature + expiration
        payload = jwt.decode(
            refresh_token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )

        # 2. Get user ID from JWT
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid refresh token"
            )

        # 3. Convert user_id to MongoDB ObjectId
        try:
            user_object_id = ObjectId(user_id)
        except Exception:
            raise HTTPException(
                status_code=401,
                detail="Invalid user ID"
            )

        # 4. Find user in MongoDB
        user_doc = await users_collection.find_one(
            {"_id": user_object_id}
        )

        if not user_doc:
            raise HTTPException(
                status_code=401,
                detail="User not found"
            )

        # 5. Get stored refresh-token hash
        stored_refresh_token = user_doc.get("refresh_token")

        if not stored_refresh_token:
            raise HTTPException(
                status_code=401,
                detail="Refresh token revoked"
            )

        # 6. Compare cookie token with DB hash
        valid_refresh_token = await run_in_threadpool(
            verify_password,
            refresh_token,
            stored_refresh_token
        )

        if not valid_refresh_token:
            raise HTTPException(
                status_code=401,
                detail="Invalid refresh token"
            )

        # 7. Create new access token
        new_access_token = create_access_token(
            user_id,
            JWT_SECRET
        )

        # 8. Create new refresh token
        new_refresh_token = create_refresh_token(
            user_id,
            JWT_SECRET
        )

        # 9. Hash new refresh token
        new_refresh_token_hash = await run_in_threadpool(
            hash_password,
            new_refresh_token
        )

        # 10. Rotate refresh token in MongoDB
        await users_collection.update_one(
            {"_id": user_object_id},
            {
                "$set": {
                    "refresh_token": new_refresh_token_hash,
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )

        # 11. Replace refresh-token cookie
        set_refresh_cookie(
            response,
            new_refresh_token
        )

        # 12. Return new access token
        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "message": "Access token created successfully"
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Refresh token expired. Login again."
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token"
        )

    except HTTPException:
        raise

    except Exception as e:
        print(f"Refresh error: {e}")

        raise HTTPException(
            status_code=500,
            detail="Refresh failed"
        )


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    try:
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=refresh_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            path="/",
        )
    except Exception as e:
        print(str(e))


@app.post("/logout")
async def logout(
    request: Request,
    response: Response
):
    refresh_token = request.cookies.get(
        REFRESH_COOKIE_NAME
    )

    if refresh_token:
        try:
            # Decode token to get user ID
            payload = jwt.decode(
                refresh_token,
                JWT_SECRET,
                algorithms=[JWT_ALGORITHM]
            )

            user_id = payload.get("sub")

            if user_id:
                await users_collection.update_one(
                    {
                        "_id": ObjectId(user_id)
                    },
                    {
                        "$set": {
                            "refresh_token": None,
                            "updated_at": datetime.now(timezone.utc)
                        }
                    }
                )

        except Exception as e:
            # Even if token is expired/invalid,
            # continue deleting the cookie.
            print(f"Logout token error: {e}")

    # Delete refresh-token cookie
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )

    return {
        "message": "Logged out successfully"
    }


@app.post("/chat")
@limiter.limit("5/minute")
async def chat(request: Request, token_data=Depends(verify_access_token)):
    try:
        user_id = token_data["sub"]
        
        body = await request.json()
        message = body.get("message")

        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        workflow = request.app.state.workflow
        response = await workflow.ainvoke(
                                        {"query": message, "user_id": user_id},
                                        config={"configurable": {"thread_id": user_id}},
                                            )
        print("workflow response:", response)
        # response = await chat_function(message, user_id)
        return {"answer": extract_response(response)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    user_id = None
    
    try:
        # Validate token
        payload = decode_token(token)
        user_id = payload["sub"]
    except jwt.InvalidTokenError:
        try:
            await websocket.close(code=1008, reason="Invalid token")
        except:
            pass
        return

    # Accept connection
    try:
        await websocket.accept()
    except Exception as e:
        print(f"Failed to accept WebSocket: {e}")
        return

    # Connect user
    await manager.connect(user_id, websocket)
    
    try:
        while True:
            # Keep connection alive by receiving data
            await websocket.receive_text()
    
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        print(f"User {user_id} disconnected")
    
    except Exception as e:
        print(f"WebSocket error: {e}")
        if user_id:
            manager.disconnect(user_id)


@app.get("/approve/{approval_id}")
async def approve(approval_id: str):
    request = await get_request(approval_id)

    if request is None:
        return {"message": "Invalid approval id"}

    if request["status"] != "PENDING":
        return {"message": f"Request already {request['status'].lower()}"}

    await update_status(approval_id, "APPROVED")

    response = await execute_approved_request(request)

    user_details = await users_collection.find_one({"_id": ObjectId(request["user_id"])})
    if user_details:
        email = user_details["email"]


    await send_answer_to_user(request['email'],request['query'],response['answer'])

    await manager.send_to_user(
        user_id=request["user_id"],
        message={
            "type": "approval_completed",
            "approval_id": approval_id,
            "query": request["query"],
            "answer": response["answer"],})
    
    return {"status": "approved", "answer": response["answer"]}


@app.get("/reject/{approval_id}", response_class=HTMLResponse)
async def reject_page(approval_id: str):

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Reject Request</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background:#f5f5f5;
                display:flex;
                justify-content:center;
                align-items:center;
                height:100vh;
                margin:0;
            }}

            .card {{
                background:white;
                width:420px;
                padding:20px;
                border-radius:8px;
                box-shadow:0 2px 10px rgba(0,0,0,.2);
            }}

            textarea {{
                width:100%;
                height:120px;
                resize:none;
                padding:10px;
                font-size:14px;
                margin-top:10px;
            }}

            button {{
                margin-top:15px;
                width:100%;
                padding:12px;
                background:#dc3545;
                color:white;
                border:none;
                border-radius:5px;
                cursor:pointer;
                font-size:16px;
            }}

            button:hover {{
                background:#b02a37;
            }}
        </style>
    </head>

    <body>

        <div class="card">

            <h2>Reject Request</h2>

            <form action="/reject/{approval_id}" method="post">

                <label><b>Reason</b></label>

                <textarea
                    name="reason"
                    required
                    placeholder="Enter rejection reason..."></textarea>

                <button type="submit">
                    Reject Request
                </button>

            </form>

        </div>

    </body>
    </html>
    """




@app.post("/reject/{approval_id}")
async def reject_request(
    approval_id: str,
    reason: str = Form(...)
):

    request = await get_request(approval_id)

    if request is None:
        return HTMLResponse("<h2>Invalid Approval ID</h2>", status_code=404)

    if request["status"] != "PENDING":
        return HTMLResponse(
            f"<h2>Request already {request['status']}</h2>"
        )

    await update_status(
        approval_id=approval_id,
        status="REJECTED")

    
    user_details = await users_collection.find_one({"_id": ObjectId(request["user_id"])})

    if user_details:
        email = user_details["email"]

    await send_rejection_email(
        receiver_email=email,
        query=request["query"],
        reason=reason
    )

    try:
        await manager.send_to_user(
                    user_id=request["user_id"],
                    message={
                        "type": "approval_rejected",
                        "approval_id": approval_id,
                        "query": request["query"],
                        "reason": reason,
                    },
                )
    except:
        pass

    return HTMLResponse("""
        <html>
        <body style="
            font-family:Arial;
            text-align:center;
            margin-top:80px;">

            <h2 style="color:red;">
                Request Rejected Successfully
            </h2>

            <p>You may now close this window.</p>

        </body>
        </html>
    """)


@app.get("/api/history/{user_id}")
async def get_history(user_id: str, request: Request, token_data=Depends(verify_access_token)):
    """Get Q&A history for a user"""
    try:
        if token_data["sub"] != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        config = {"configurable": {"thread_id": user_id}}
        workflow = request.app.state.workflow

        history = []
        async for state in workflow.aget_state_history(config):
            values = state.values

            if ("query" in values and "answer" in values):
                history.append({
                    "query": values["query"],
                    "answer": values["answer"]
                })
            

        print('response:',history)

        return {
            "status": 200,
            "user_id": user_id,
            "history": history}

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
  

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
