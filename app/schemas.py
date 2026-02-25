from pydantic import BaseModel, Field

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


class ChatResponse(BaseModel):
    response: str
