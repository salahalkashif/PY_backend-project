from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


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


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    conversation_id: UUID
    created_at: datetime
    messages: list[MessageOut]


class UserChatsResponse(BaseModel):
    conversations: list[ConversationOut]


class EmbeddingCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class EmbeddingCreateResponse(BaseModel):
    id: UUID
    content: str
    embedding_dimensions: int
