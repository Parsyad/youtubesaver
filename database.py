import os
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Try multiple possible environment variable names
DATABASE_URL = (
    os.environ.get('DATABASE_PUBLIC_URL') or 
    os.environ.get('DATABASE_URL') or 
    os.environ.get('PGDATABASE_URL')
)

if not DATABASE_URL:
    print("WARNING: No database URL found. Running without database.")
    engine = None
    SessionLocal = None
else:
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, unique=True, index=True)
    username = Column(String, nullable=True)
    first_used = Column(DateTime, server_default=func.now())
    last_active = Column(DateTime, onupdate=func.now())

class Download(Base):
    __tablename__ = "downloads"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    url = Column(String)
    file_size = Column(Integer, nullable=True)
    timestamp = Column(DateTime, server_default=func.now())

def init_db():
    if engine:
        Base.metadata.create_all(bind=engine)

def register_user(user_id, username=None, first_name=None):  # Added first_name
    if not SessionLocal:
        return False
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            user = User(user_id=user_id, username=username)
            db.add(user)
            db.commit()
            return True
        return False
    finally:
        db.close()

def update_user_activity(user_id):
    if not SessionLocal:
        return
    db = SessionLocal()
    try:
        db.query(User).filter(User.user_id == user_id).update({"last_active": func.now()})
        db.commit()
    finally:
        db.close()

def increment_download_count(user_id):
    pass

def log_download(user_id, url, file_size=None):
    if not SessionLocal:
        return
    db = SessionLocal()
    try:
        download = Download(user_id=user_id, url=url, file_size=file_size)
        db.add(download)
        db.commit()
    finally:
        db.close()

def get_stats():
    if not SessionLocal:
        return {"users": 0, "downloads": 0}
    db = SessionLocal()
    try:
        users_count = db.query(User).count()
        downloads_count = db.query(Download).count()
        return {"users": users_count, "downloads": downloads_count}
    finally:
        db.close()
