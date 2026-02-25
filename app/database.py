from dotenv import load_dotenv
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()



DATABASE_URL = "postgresql://postgres.hqjbhdsiaewmnmemffzv:kQi1HoSfvvUwmarn@aws-1-eu-north-1.pooler.supabase.com:6543/postgres"


if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()
