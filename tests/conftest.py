from __future__ import annotations
import pytest
from app import create_app
from app.extensions import db as _db
from app.models.user import User


@pytest.fixture(scope="session")
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope="session")
def db(app):
    return _db


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


@pytest.fixture(scope="function")
def auth_client(app):
    """Client with a logged-in regular user."""
    with app.app_context():
        user = User.query.filter_by(
            email="authuser@example.com"
        ).first()
        if not user:
            user = User(
                username="authuser",
                email="authuser@example.com",
                full_name="Auth User",
                role="user",
                is_active=True,
                is_verified=True,
            )
            user.set_password("StrongPass123!")
            _db.session.add(user)
            _db.session.commit()

    client = app.test_client()
    client.post("/auth/login", json={
        "email": "authuser@example.com",
        "password": "StrongPass123!",
    })
    return client


@pytest.fixture(scope="function")
def admin_client(app):
    """Client with a logged-in admin user."""
    with app.app_context():
        admin = User.query.filter_by(
            email="admin@example.com"
        ).first()
        if not admin:
            admin = User(
                username="adminuser",
                email="admin@example.com",
                full_name="Admin User",
                role="admin",
                is_active=True,
                is_verified=True,
            )
            admin.set_password("AdminPass123!")
            _db.session.add(admin)
            _db.session.commit()

    client = app.test_client()
    client.post("/auth/login", json={
        "email": "admin@example.com",
        "password": "AdminPass123!",
    })
    return client


@pytest.fixture(scope="function")
def recruiter_client(app):
    """Client with a logged-in recruiter user."""
    with app.app_context():
        recruiter = User.query.filter_by(
            email="recruiter@example.com"
        ).first()
        if not recruiter:
            recruiter = User(
                username="recruiteruser",
                email="recruiter@example.com",
                full_name="Recruiter User",
                role="recruiter",
                is_active=True,
                is_verified=True,
            )
            recruiter.set_password("RecruiterPass123!")
            _db.session.add(recruiter)
            _db.session.commit()

    client = app.test_client()
    client.post("/auth/login", json={
        "email": "recruiter@example.com",
        "password": "RecruiterPass123!",
    })
    return client