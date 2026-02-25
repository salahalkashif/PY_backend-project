from app.database import engine, SessionLocal
from app.models import Base, User
from app.schemas import UserCreate, UserResponse
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

# =========================
# FastAPI App
# =========================

app = FastAPI()

# =========================
# Create Tables
# =========================

Base.metadata.create_all(bind=engine)

# =========================
# Database Dependency
# =========================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =========================
# POST - Insert User
# =========================

@app.post("/users", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = User(name=user.name, age=user.age)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# =========================
# GET - Retrieve User by ID
# =========================

@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# =========================
# PUT - Update User
# =========================

@app.put("/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    db_user.name = user.name
    db_user.age = user.age
    db.commit()
    db.refresh(db_user)
    return db_user

# =========================
# DELETE - Delete User
# =========================

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(db_user)
    db.commit()
    return {"detail": "User deleted successfully"}