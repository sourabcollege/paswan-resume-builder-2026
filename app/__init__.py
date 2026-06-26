import os
from pathlib import Path

from flask import Flask
from app.extensions import db, migrate, login_manager, csrf, limiter, mail, oauth

from app.profile import bp as profile_bp


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    base_dir   = Path(__file__).resolve().parent
    project_root = base_dir.parent
    template_dir = str(project_root / "templates")
    static_dir   = str(project_root / "static")

    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir,
        instance_relative_config=True,
    )

    from app.config import config_by_name, DevelopmentConfig
    cfg_class = config_by_name.get(config_name.lower(), DevelopmentConfig)
    app.config.from_object(cfg_class)

    if hasattr(cfg_class, "init_app"):
        cfg_class.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    oauth.init_app(app)

    # Register Google OAuth
    oauth.register(
        name='google',
        client_id=app.config.get('GOOGLE_CLIENT_ID'),
        client_secret=app.config.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.models import (
        User, Resume, ResumeVersion, ResumeSection,
        Job, ResumeScore, JobMatch, AnalyticsHistory,
        ActivityLog, Subscription, Payment,
    )

    from app.main      import bp as main_bp
    from app.auth      import bp as auth_bp
    from app.resume    import bp as resume_bp
    from app.jobs      import bp as jobs_bp
    from app.analytics import bp as analytics_bp
    from app.ai        import bp as ai_bp
    from app.admin     import bp as admin_bp
    from app.recruiter import bp as recruiter_bp
    from app.payment   import bp as payment_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp,      url_prefix="/auth")
    app.register_blueprint(resume_bp,    url_prefix="/resume")
    app.register_blueprint(jobs_bp,      url_prefix="/jobs")
    app.register_blueprint(analytics_bp, url_prefix="/analytics")
    app.register_blueprint(profile_bp, url_prefix="/profile")
    app.register_blueprint(ai_bp,        url_prefix="/ai")
    app.register_blueprint(admin_bp,     url_prefix="/admin")
    app.register_blueprint(recruiter_bp, url_prefix="/recruiter")
    app.register_blueprint(payment_bp,   url_prefix="/payment")

    return app