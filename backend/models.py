# from pydantic import BaseModel, EmailStr,Field
# from datetime import datetime
# from typing import Literal,TypedDict


# class RegisterRequest(BaseModel):
#     username: str
#     email: EmailStr
#     password: str
#     current_datetime: datetime = Field(default_factory=datetime.now)
#     updated_datetime: datetime = Field(default_factory=datetime.now)


# class LoginRequest(BaseModel):
#     email: EmailStr
#     password: str


# class CategorizeQuery(BaseModel):
#     category: Literal['SAFE','UNSAFE'] = Field(description= "UNSAFE if question is dangerous, harmful else SAFE.")


# class ChatState(TypedDict, total=False):
#     query: str
#     category: str
#     answer: str
#     status: str
#     approval_id: str
#     message: str
#     user_id: str
#     reason: str