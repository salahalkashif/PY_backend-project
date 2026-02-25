from pydantic import BaseModel, ConfigDict

class UserCreate(BaseModel):
    name: str
    age: int

class UserResponse(UserCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)
