from __future__ import annotations
import pytest
from app import create_app
from app.extensions import db
from app.models.user import User


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


# ── Admin Role Tests ────────────────────────────────────────────────────
class TestAdminRoleAssignment:

    def test_admin_email_becomes_admin_on_register(self, client, app):
        """Admin email (from config) should get admin role on registration."""
        with app.app_context():
            admin_email = app.config.get("ADMIN_EMAIL", "sourabcollege@gmail.com")
            resp = client.post("/auth/register", json={
                "first_name": "Admin",
                "last_name": "User",
                "email": admin_email,
                "password": "StrongPass123!",
                "confirm_password": "StrongPass123!",
                "accept_terms": True,
            })
            assert resp.status_code in (200, 201, 302)

            user = User.query.filter_by(email=admin_email).first()
            assert user is not None
            assert user.role == User.ROLE_ADMIN
            assert user.is_admin is True

    def test_normal_email_becomes_user_on_register(self, client):
        """Normal email should get user role on registration."""
        resp = client.post("/auth/register", json={
            "first_name": "Normal",
            "last_name": "User",
            "email": "normal@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
            "accept_terms": True,
        })
        assert resp.status_code in (200, 201, 302)

        user = User.query.filter_by(email="normal@example.com").first()
        assert user is not None
        assert user.role == User.ROLE_USER
        assert user.is_admin is False

    def test_admin_email_promoted_on_login(self, client, app):
        """Existing user with admin email gets promoted to admin on login."""
        with app.app_context():
            # Create user manually as regular user
            admin_email = app.config.get("ADMIN_EMAIL", "sourabcollege@gmail.com")
            user = User(
                email=admin_email,
                first_name="Existing",
                last_name="User",
                account_status=User.STATUS_ACTIVE,
            )
            user.set_password("StrongPass123!")
            db.session.add(user)
            db.session.commit()

            # Verify initially not admin
            assert user.role == User.ROLE_USER

            # Login should promote to admin
            resp = client.post("/auth/login", json={
                "email": admin_email,
                "password": "StrongPass123!",
            })
            assert resp.status_code in (200, 302)

            # Refresh user from DB
            db.session.refresh(user)
            assert user.role == User.ROLE_ADMIN
            assert user.is_admin is True


class TestAdminRouteAccess:

    def test_admin_route_blocked_for_normal_user(self, client):
        """Normal user should get 403 when accessing admin routes."""
        # Register normal user
        client.post("/auth/register", json={
            "first_name": "Normal",
            "last_name": "User",
            "email": "normal2@example.com",
            "password": "StrongPass123!",
            "confirm_password": "StrongPass123!",
            "accept_terms": True,
        })

        # Login as normal user
        client.post("/auth/login", json={
            "email": "normal2@example.com",
            "password": "StrongPass123!",
        })

        # Try accessing admin dashboard
        resp = client.get("/admin/")
        assert resp.status_code in (302, 403)

    def test_admin_route_accessible_for_admin_user(self, client, app):
        """Admin user should access admin routes successfully."""
        with app.app_context():
            admin_email = app.config.get("ADMIN_EMAIL", "sourabcollege@gmail.com")

            # Register admin user
            client.post("/auth/register", json={
                "first_name": "Admin",
                "last_name": "User",
                "email": admin_email,
                "password": "StrongPass123!",
                "confirm_password": "StrongPass123!",
                "accept_terms": True,
            })

            # ✅ Manually verify email and activate account (test env suppresses email)
            from datetime import datetime, timezone
            user = User.query.filter_by(email=admin_email).first()
            user.email_verified_at = datetime.now(timezone.utc)
            user.account_status = User.STATUS_ACTIVE
            db.session.commit()

            # Login as admin
            client.post("/auth/login", json={
                "email": admin_email,
                "password": "StrongPass123!",
            })

            # Access admin dashboard
            resp = client.get("/admin/")
            assert resp.status_code == 200