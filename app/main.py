import os
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext
import cohere
from app.models import Message, Conversation, Embedding, EMBEDDING_DIMENSIONS, Video
from app.schemas import ChatRequest, ChatResponse, UserChatsResponse, VideoIngestResponse
from app.database import SessionLocal, engine
from app.models import Base, User
from app.schemas import (
    UserCreate,
    UserResponse,
    Token,
    EmbeddingCreateRequest,
    EmbeddingCreateResponse,
)
from app.video_processing import (
    is_valid_video_url,
    process_video_pipeline,
    save_uploaded_video,
    validate_video_upload,
)
from dotenv import load_dotenv
load_dotenv()
co = cohere.Client(os.getenv("COHERE_API_KEY"))


# =========================
# Settings
# =========================

SECRET_KEY = "supersecretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

with engine.begin() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
Base.metadata.create_all(bind=engine)

app = FastAPI()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# =========================
# Dependency
# =========================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =========================
# Helper Functions
# =========================

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.name == username).first()
    if user is None:
        raise credentials_exception
    return user


# =========================
# Register
# =========================

@app.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.name == user.name).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_password = get_password_hash(user.password)

    new_user = User(name=user.name, password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# =========================
# Login
# =========================

@app.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.name == form_data.username).first()

    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": user.name})
    return {"access_token": access_token, "token_type": "bearer"}


# =========================
# Protected Example Endpoint
# =========================

@app.get("/users/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user



#Video ingestion
@app.post("/videos", response_model=VideoIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_video(
    background_tasks: BackgroundTasks,
    video_file: UploadFile | None = File(default=None),
    video_url: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    if video_file and video_url:
        raise HTTPException(status_code=422, detail="Provide either video_file or video_url, not both")
    if not video_file and not video_url:
        raise HTTPException(status_code=422, detail="Either video_file or video_url is required")
    if video_url and not is_valid_video_url(video_url):
        raise HTTPException(status_code=422, detail="Invalid video_url format")
    if video_file:
        validate_video_upload(video_file)

    video = Video(
        original_url=video_url,
        status="processing",
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    if video_file:
        local_path, title = save_uploaded_video(video_file=video_file, video_id=video.id)
        video.local_path = local_path
        video.title = title
        db.commit()
        db.refresh(video)

    background_tasks.add_task(
        process_video_pipeline,
        video_id=video.id,
        db_session_factory=SessionLocal,
        source_type="upload" if video_file else "url",
        upload_path=video.local_path,
        video_url=video_url,
        llm_fn=call_llm,
    )

    return {"video_id": video.id, "status": "processing"}


#Chat history
def call_llm(chat_history: list):

    last_user_message = chat_history[-1]["content"]

    previous_chat = [
        {
            "role": msg["role"],
            "message": msg["content"]
        }
        for msg in chat_history[:-1]
    ]

    response = co.chat(
        model="command-r-08-2024",
        message=last_user_message,
        chat_history=previous_chat
    )

    return response.text








#Chat endpoints
@app.post("/chat")
def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="message is required")

    conversation = None

    if request.conversation_id:
        conversation = db.query(Conversation).filter(
            Conversation.id == request.conversation_id,
            Conversation.user_id == current_user.id
        ).first()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

    else:
        conversation = Conversation(user_id=current_user.id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    previous_messages = db.query(Message)\
        .filter(Message.conversation_id == conversation.id)\
        .order_by(Message.created_at)\
        .all()

    chat_history = []

    for msg in previous_messages:
        chat_history.append({
            "role": "USER" if msg.role == "user" else "CHATBOT",
            "content": msg.content
        })

    chat_history.append({
        "role": "USER",
        "content": message
    })


    ai_response = call_llm(chat_history)


    user_msg = Message(
        conversation_id=conversation.id,
        role="user",
        content=message
    )
    db.add(user_msg)


    ai_msg = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=ai_response
    )
    db.add(ai_msg)

    db.commit()

    return {
        "conversation_id": str(conversation.id),
        "response": ai_response
    }


@app.get("/users/me/chats", response_model=UserChatsResponse)
@app.get("/chats", response_model=UserChatsResponse)
def get_user_chats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.created_at).all()

    result = []
    for conversation in conversations:
        messages = db.query(Message).filter(
            Message.conversation_id == conversation.id
        ).order_by(Message.created_at).all()

        result.append({
            "conversation_id": conversation.id,
            "created_at": conversation.created_at,
            "messages": [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "created_at": msg.created_at
                }
                for msg in messages
            ]
        })

    return {"conversations": result}


def get_text_embedding(content: str) -> list[float]:
    payload = {
        "model": "embed-english-v3.0",
        "texts": [content],
        "input_type": "search_document",
        "embedding_types": ["float"],
        "output_dimension": EMBEDDING_DIMENSIONS,
    }

    try:
        response = co.embed(**payload)
    except TypeError:
        payload.pop("output_dimension", None)
        response = co.embed(**payload)

    embeddings = getattr(response, "embeddings", None)
    if embeddings is None:
        raise RuntimeError("Cohere response did not include embeddings")

    if isinstance(embeddings, list):
        vector = embeddings[0]
    elif hasattr(embeddings, "float"):
        vector = embeddings.float[0]
    elif isinstance(embeddings, dict) and "float" in embeddings:
        vector = embeddings["float"][0]
    else:
        raise RuntimeError("Unsupported embedding response format")

    return [float(v) for v in vector]


@app.post("/embeddings", response_model=EmbeddingCreateResponse, status_code=status.HTTP_201_CREATED)
def create_embedding(
    request: EmbeddingCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = request.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="content is required")

    try:
        vector = get_text_embedding(content)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate embedding: {exc}")

    if len(vector) != EMBEDDING_DIMENSIONS:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected embedding size {len(vector)}; expected {EMBEDDING_DIMENSIONS}",
        )

    new_embedding = Embedding(content=content, embedding=vector)
    db.add(new_embedding)
    db.commit()
    db.refresh(new_embedding)

    return {
        "id": new_embedding.id,
        "content": new_embedding.content,
        "embedding_dimensions": len(vector),
    }
