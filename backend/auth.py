from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import User, UserSession, utcnow


class AuthenticationError(RuntimeError):
    """로그인 또는 세션 검증 실패를 나타낸다."""


@dataclass(frozen=True)
class GoogleProfile:
    sub: str
    email: str
    name: str


@dataclass(frozen=True)
class AuthenticatedSession:
    session_token: str
    user: User


class GoogleIdentityService:
    """구글 access token으로 사용자 프로필을 조회한다."""

    def fetch_profile(self, access_token: str) -> GoogleProfile:
        try:
            response = httpx.get(
                settings.google_userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AuthenticationError("Google access token verification failed.") from exc

        payload = response.json()
        sub = str(payload.get("sub", "")).strip()
        email = str(payload.get("email", "")).strip()
        name = str(payload.get("name", "")).strip() or email or "Google User"

        if not sub or not email:
            raise AuthenticationError("Google profile response was missing required fields.")

        return GoogleProfile(sub=sub, email=email, name=name)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _build_session_token() -> str:
    return "bp_" + secrets.token_urlsafe(32)


def purge_expired_sessions(db: Session) -> None:
    now = utcnow()
    expired_sessions = db.scalars(
        select(UserSession).where(UserSession.expires_at <= now)
    ).all()

    for session in expired_sessions:
        db.delete(session)

    if expired_sessions:
        db.commit()


def authenticate_google_access_token(
    db: Session,
    access_token: str,
    identity_service: GoogleIdentityService | None = None,
) -> AuthenticatedSession:
    service = identity_service or GoogleIdentityService()
    profile = service.fetch_profile(access_token)
    purge_expired_sessions(db)

    user = db.scalar(select(User).where(User.google_sub == profile.sub))
    if user is None:
        user = User(
            google_sub=profile.sub,
            email=profile.email,
            display_name=profile.name,
        )
        db.add(user)
        db.flush()
    else:
        user.email = profile.email
        user.display_name = profile.name

    raw_session_token = _build_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=_hash_token(raw_session_token),
            expires_at=utcnow() + timedelta(days=settings.session_duration_days),
        )
    )
    db.commit()
    db.refresh(user)

    return AuthenticatedSession(session_token=raw_session_token, user=user)


def get_user_for_session_token(db: Session, session_token: str) -> User:
    purge_expired_sessions(db)
    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == _hash_token(session_token))
    )
    if session is None:
        raise AuthenticationError("Session token is invalid or expired.")

    user = db.get(User, session.user_id)
    if user is None:
        raise AuthenticationError("Session user could not be found.")

    return user


def revoke_session_token(db: Session, session_token: str) -> None:
    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == _hash_token(session_token))
    )
    if session is not None:
        db.delete(session)
        db.commit()
