from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID


class UserCreate(BaseModel):
    name: str
    password: str = Field(..., min_length=6, max_length=72)



class UserResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


#  Login
class Token(BaseModel):
    access_token: str
    token_type: str


#for llm

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[UUID] = None


class ChatResponse(BaseModel):
    response: str
