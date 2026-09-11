from pydantic import BaseModel, EmailStr, Field
from typing import Literal, TypedDict

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str



class CategorizeQuery(BaseModel):
    category: Literal['SAFE','UNSAFE'] = Field(description= "UNSAFE if question is dangerous, harmful else SAFE.")


class ChatState(TypedDict, total=False):
    query: str
    category: str
    answer: str
    status: str
    approval_id: str
    message: str
    user_id: str
    reason: str