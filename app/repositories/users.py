from __future__ import annotations

from sqlalchemy import func

from app.extensions import db
from app.models.user import User


class UserRepository:
    def get_by_id(self, user_id: int) -> User | None:
        return db.session.get(User, user_id)

    def get_by_public_id(self, public_id: str) -> User | None:
        return User.query.filter_by(public_id=public_id).one_or_none()

    def get_by_email(self, email: str) -> User | None:
        normalized = self.normalize_email(email)
        return User.query.filter(func.lower(User.email) == normalized).one_or_none()

    def email_exists(self, email: str) -> bool:
        normalized = self.normalize_email(email)
        return db.session.query(User.id).filter(func.lower(User.email) == normalized).first() is not None

    def add(self, user: User) -> User:
        db.session.add(user)
        return user

    def save(self, user: User) -> User:
        db.session.add(user)
        return user

    @staticmethod
    def normalize_email(email: str) -> str:
        return (email or "").strip().lower()
