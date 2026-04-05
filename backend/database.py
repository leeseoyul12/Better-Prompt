from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import settings


logger = logging.getLogger("better_prompt.database")
SQLITE_FALLBACK_URL = "sqlite:///./backend/better_prompt.sqlite3"


class Base(DeclarativeBase):
    """SQLAlchemy 기본 베이스 클래스다."""


def utcnow() -> datetime:
    """timezone-aware now를 사용하되 DB에는 naive UTC로 저장한다."""
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    """구글 로그인 사용자 정보를 저장한다."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    saved_prompts: Mapped[list["SavedPrompt"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserSession(Base):
    """서비스 세션 토큰의 해시값만 저장한다."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")


class SavedPrompt(Base):
    """사용자가 저장한 프롬프트 본문과 제목을 저장한다."""

    __tablename__ = "saved_prompts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
    )

    user: Mapped[User] = relationship(back_populates="saved_prompts")


def _build_engine_kwargs(database_url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"future": True}
    if database_url.startswith("sqlite"):
        # SQLite 테스트 환경에서는 같은 스레드 제한을 풀어야 TestClient와 함께 동작한다.
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


def _create_database_engine():
    database_url = settings.database_url
    try:
        engine = create_engine(database_url, **_build_engine_kwargs(database_url))
        if database_url.startswith("postgresql"):
            with engine.connect() as connection:
                connection.close()
        return engine
    except Exception:
        if database_url.startswith("postgresql"):
            logger.warning(
                "postgres_driver_unavailable fallback_url=%s sqlite_url=%s",
                database_url,
                SQLITE_FALLBACK_URL,
            )
            return create_engine(
                SQLITE_FALLBACK_URL,
                **_build_engine_kwargs(SQLITE_FALLBACK_URL),
            )
        raise


engine = _create_database_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_database() -> None:
    """테이블이 없으면 생성한다."""
    Base.metadata.create_all(bind=engine)
