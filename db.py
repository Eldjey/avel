# db.py
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

Base = declarative_base()
engine = create_engine("sqlite:///avel_tournament.db", echo=False)
Session = sessionmaker(bind=engine)
session = Session()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True)
    custom_id = Column(String, unique=True)
    username = Column(String)
    fullname = Column(String, default="")
    nickname = Column(String, default="")  # ✅ YANGI USTUN
    score = Column(Integer, default=0)
    tournaments_played = Column(Integer, default=0)
    language = Column(String, default='uz')

class Tournament(Base):
    __tablename__ = "tournaments"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    final_teams = Column(String)
    score_summary = Column(String)
    mvp_user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(DateTime)

    mvp = relationship("User", foreign_keys=[mvp_user_id])

def init_db():
    Base.metadata.create_all(engine)

def reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

def get_or_create_user(tg_id, username):
    user = session.query(User).filter_by(tg_id=tg_id).first()
    if not user:
        user = User(tg_id=tg_id, username=username)
        session.add(user)
        session.commit()
    return user

def get_rank(score):
    if score >= 10000:
        return "🐦‍🔥Генерал (S)"
    elif score >= 3001:
        return "🎖🎖🎖🎖🎖🎖 Полковник (AA)"
    elif score >= 1801:
        return "🎖🎖🎖🎖🎖 Майор (A)"
    elif score >= 1001:
        return "🎖🎖🎖🎖 Капитан (B)"
    elif score >= 501:
        return "🎖🎖🎖 Лейтенант (D)"
    elif score >= 201:
        return "🎖🎖 Сержант (C)"
    elif score >= 35:
        return "🎖 Капрал (E)"
    else:
        return "🔘 Новичок"

def add_score(custom_id, score_to_add):
    user = session.query(User).filter_by(custom_id=custom_id).first()
    if user:
        user.score += score_to_add
        session.commit()
        return user
    return None

def get_top_users(limit=5):
    return session.query(User).order_by(User.score.desc()).limit(limit).all()

def get_user_rank(user):
    users = session.query(User).order_by(User.score.desc()).all()
    for i, u in enumerate(users, start=1):
        if u.id == user.id:
            return i
    return -1

def list_tournaments():
    return session.query(Tournament).order_by(Tournament.date.desc()).all()
