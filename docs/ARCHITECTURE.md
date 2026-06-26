# Paswan Resume Builder v2.0 Architecture

## System Architecture Diagram

```text
+-----------------------------------------------------------------------------+
|                              Client Layer                                    |
|                                                                             |
|  HTML5 + CSS3 + Vanilla JavaScript                                           |
|  Fetch API, CSRF-aware forms, Chart.js dashboards, responsive glass UI        |
+--------------------------------+--------------------------------------------+
                                 | HTTPS
                                 v
+-----------------------------------------------------------------------------+
|                         Nginx Reverse Proxy                                  |
|                                                                             |
|  TLS termination, gzip, static asset caching, upload size limits, headers     |
+--------------------------------+--------------------------------------------+
                                 | WSGI
                                 v
+-----------------------------------------------------------------------------+
|                         Flask Application                                    |
|                                                                             |
|  Application factory, Blueprints, Flask-Login, Flask-WTF, Flask-Limiter       |
|  Security headers, structured logging, RBAC, ownership decorators             |
|  Thin routes -> app/services business logic -> repositories -> models         |
|                                                                             |
|  Blueprints                                                                  |
|  - auth: registration, login, verification, reset, profile                    |
|  - resume: upload, parse, build, version, export                              |
|  - jobs: job listings, match scoring, applications                            |
|  - analytics: trends, completeness, skill breakdowns                          |
|  - ai: enhancement requests and result retrieval                              |
|  - recruiter: candidate search, shortlist, notes, downloads                   |
|  - admin: users, jobs, logs, revenue, health                                  |
|  - payments: Razorpay, Stripe, subscriptions, webhooks                        |
+----------------+--------------------------+---------------------------------+
                 |                          |
                 | SQLAlchemy ORM           | Celery tasks
                 v                          v
+-------------------------------+   +-----------------------------------------+
|          Database              |   |              Worker Layer               |
|                                |   |                                         |
|  SQLite for development        |   |  PDF generation, DOCX export, emails,   |
|  PostgreSQL for production     |   |  AI requests, weekly analytics summaries|
|                                |   |                                         |
|  Users, resumes, versions,     |   |  Redis broker/result backend            |
|  scores, jobs, matches, logs,  |   +-------------------+---------------------+
|  subscriptions, payments       |                       |
+----------------+---------------+                       |
                 |                                       |
                 v                                       v
+-------------------------------+   +-----------------------------------------+
|       Storage Abstraction      |   |          External Integrations          |
|                                |   |                                         |
|  Local filesystem in dev       |   |  SMTP, OpenAI/OpenRouter-compatible API,|
|  S3/R2-compatible in prod      |   |  Razorpay, Stripe                       |
|                                |   |                                         |
|  uploads/resumes/{user_id}/    |   |  AI is enhancement-only; offline engines|
|  uploads/avatars/{user_id}/    |   |  keep core product functional           |
|  generated_resumes/{user_id}/  |   +-----------------------------------------+
+-------------------------------+
```

## Core Runtime Boundaries

- Routes validate request intent, authentication, authorization, CSRF, rate limits, and ownership.
- Blueprint-specific helpers stay minimal and close to HTTP concerns such as forms, decorators, and response shaping.
- Top-level services in app/services/ hold core business workflows such as resume creation, parsing, matching, exports, payments, and analytics.
- Repositories in app/repositories/ isolate database access for users, resumes, jobs, analytics, and payments.
- Offline engines are deterministic pure-Python modules for ATS scoring, skill extraction, keyword matching, job matching, gap analysis, and completeness scoring.
- Integrations isolate external systems so OpenAI/OpenRouter, payment providers, SMTP, Redis, and object storage can fail without breaking core resume workflows.
- Models live in app/models/ as focused modules and define persistence only; route handlers do not contain scoring, parsing, payment, email, or export business logic.

## Complete Folder Structure Tree

```text
paswan-resume-builder/
|-- app.py
|-- config.py
|-- celery_app.py
|-- requirements.txt
|-- Procfile
|-- Dockerfile
|-- docker-compose.yml
|-- docker-compose.prod.yml
|-- nginx.conf
|-- .dockerignore
|-- .env.example
|-- .github/
|   `-- workflows/
|       `-- ci.yml
|-- docs/
|   `-- ARCHITECTURE.md
|-- migrations/
|-- logs/
|   |-- .gitkeep
|   |-- app.log
|   |-- error.log
|   `-- security.log
|-- uploads/
|   |-- .gitkeep
|   |-- avatars/
|   `-- resumes/
|-- generated_resumes/
|   `-- .gitkeep
|-- app/
|   |-- __init__.py
|   |-- extensions.py
|   |-- errors.py
|   |-- logging_config.py
|   |-- security.py
|   |-- models/
|   |   |-- __init__.py
|   |   |-- user.py
|   |   |-- resume.py
|   |   |-- job.py
|   |   |-- analytics.py
|   |   |-- activity.py
|   |   |-- subscription.py
|   |   `-- payment.py
|   |-- repositories/
|   |   |-- __init__.py
|   |   |-- users.py
|   |   |-- resumes.py
|   |   |-- jobs.py
|   |   |-- analytics.py
|   |   `-- payments.py
|   |-- services/
|   |   |-- __init__.py
|   |   |-- auth_service.py
|   |   |-- resume_service.py
|   |   |-- parsing_service.py
|   |   |-- export_service.py
|   |   |-- job_match_service.py
|   |   |-- analytics_service.py
|   |   |-- ai_service.py
|   |   |-- recruiter_service.py
|   |   |-- admin_service.py
|   |   |-- payment_service.py
|   |   `-- notification_service.py
|   |-- auth/
|   |   |-- __init__.py
|   |   |-- routes.py
|   |   |-- forms.py
|   |   `-- decorators.py
|   |-- resume/
|   |   |-- __init__.py
|   |   |-- routes.py
|   |   `-- forms.py
|   |-- jobs/
|   |   |-- __init__.py
|   |   |-- routes.py
|   |   `-- forms.py
|   |-- analytics/
|   |   |-- __init__.py
|   |   `-- routes.py
|   |-- ai/
|   |   |-- __init__.py
|   |   |-- routes.py
|   |   `-- tasks.py
|   |-- recruiter/
|   |   |-- __init__.py
|   |   |-- routes.py
|   |   `-- forms.py
|   |-- admin/
|   |   |-- __init__.py
|   |   |-- routes.py
|   |   `-- forms.py
|   |-- payments/
|   |   |-- __init__.py
|   |   |-- routes.py
|   |   `-- webhooks.py
|   |-- api/
|   |   |-- __init__.py
|   |   |-- routes.py
|   |   `-- tokens.py
|   |-- email/
|   |   |-- __init__.py
|   |   |-- services.py
|   |   `-- templates.py
|   |-- storage/
|   |   |-- __init__.py
|   |   |-- base.py
|   |   |-- local.py
|   |   `-- s3.py
|   |-- utils/
|   |   |-- __init__.py
|   |   |-- offline_engines.py
|   |   |-- file_validation.py
|   |   |-- parsers.py
|   |   |-- exports.py
|   |   |-- tokens.py
|   |   `-- audit.py
|   |-- static/
|   |   |-- css/
|   |   |   |-- base.css
|   |   |   |-- dashboard.css
|   |   |   |-- builder.css
|   |   |   `-- admin.css
|   |   |-- js/
|   |   |   |-- api.js
|   |   |   |-- dashboard.js
|   |   |   |-- builder.js
|   |   |   |-- analytics.js
|   |   |   |-- recruiter.js
|   |   |   `-- admin.js
|   |   `-- images/
|   |       `-- .gitkeep
|   `-- templates/
|       |-- base.html
|       |-- errors/
|       |   |-- 400.html
|       |   |-- 403.html
|       |   |-- 404.html
|       |   `-- 500.html
|       |-- auth/
|       |-- resume/
|       |-- jobs/
|       |-- analytics/
|       |-- ai/
|       |-- recruiter/
|       |-- admin/
|       |-- payments/
|       |-- emails/
|       `-- exports/
`-- tests/
    |-- conftest.py
    |-- unit/
    |   |-- test_ats_scoring.py
    |   |-- test_skill_extraction.py
    |   |-- test_keyword_matching.py
    |   |-- test_job_matching.py
    |   `-- test_completeness.py
    |-- integration/
    |   |-- test_auth_flow.py
    |   |-- test_resume_upload.py
    |   |-- test_ats_endpoint.py
    |   `-- test_job_match_endpoint.py
    `-- security/
        |-- test_csrf.py
        |-- test_authorization.py
        |-- test_file_upload_validation.py
        `-- test_rate_limiting.py
```
