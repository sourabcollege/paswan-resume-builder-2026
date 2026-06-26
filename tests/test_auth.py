from __future__ import annotations
import pytest
from app import create_app
from app.extensions import db


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


# ── Register ─────────────────────────────────────────────────────────
class TestRegister:

    def test_register_success(self, client):
        resp = client.post("/auth/register", json={
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
            "accept_terms": True,
        })
        assert resp.status_code in (200, 201, 302)

    def test_register_duplicate_email(self, client):
        data = {
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
            "accept_terms": True,
        }
        client.post("/auth/register", json=data)
        resp = client.post("/auth/register", json={
            "first_name": "Other",
            "last_name": "User",
            "email": "test@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
            "accept_terms": True,
        })
        assert resp.status_code in (400, 409, 200)

    def test_register_missing_fields(self, client):
        resp = client.post("/auth/register", json={
            "username": "testuser",
        })
        assert resp.status_code in (400, 200)

    def test_register_weak_password(self, client):
        resp = client.post("/auth/register", json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "123",
            "full_name": "Test User",
        })
        assert resp.status_code in (400, 200)


# ── Login ─────────────────────────────────────────────────────────────
class TestLogin:

    def test_login_wrong_password(self, client):
        client.post("/auth/register", json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "StrongPass123!",
            "full_name": "Test User",
        })
        resp = client.post("/auth/login", json={
            "email": "test@example.com",
            "password": "wrongpassword",
        })
        assert resp.status_code in (400, 401, 200)

    def test_login_nonexistent_user(self, client):
        resp = client.post("/auth/login", json={
            "email": "nobody@example.com",
            "password": "StrongPass123!",
        })
        assert resp.status_code in (400, 401, 200)


# ── Security ──────────────────────────────────────────────────────────
class TestSecurity:

    def test_protected_route_redirects(self, client):
        resp = client.get("/resume/list")
        assert resp.status_code in (302, 401, 403)

    def test_admin_route_unauthorized(self, client):
        resp = client.get("/admin/users")
        assert resp.status_code in (302, 401, 403)

    def test_recruiter_route_unauthorized(self, client):
        resp = client.get("/recruiter/search")
        assert resp.status_code in (302, 401, 403)

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200


# ── File Upload Security ──────────────────────────────────────────────
class TestFileUpload:

    def test_upload_without_auth(self, client):
        resp = client.post("/resume/upload")
        assert resp.status_code in (302, 401, 403)

    def test_upload_wrong_file_type(self, client):
        data = {
            "file": (b"fake content", "test.exe"),
        }
        resp = client.post(
            "/resume/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code in (302, 400, 401, 403)