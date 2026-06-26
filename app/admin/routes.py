from __future__ import annotations

from app.admin import bp
from flask import jsonify, request, render_template
from flask_login import login_required, current_user
from app.auth.decorators import admin_required
from app.services.admin_service import AdminService


@bp.route("/", methods=["GET"])
@login_required
@admin_required
def dashboard():
    """Admin dashboard landing page with safe stats."""
    stats = _safe_stats()
    return render_template("admin/dashboard.html", stats=stats)


@bp.route("/users", methods=["GET"])
@login_required
@admin_required
def get_users_api():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "")
    result = AdminService.get_all_users(page, per_page, search)
    return jsonify(result), 200


@bp.route("/users/manage", methods=["GET"])
@login_required
@admin_required
def manage_users():
    """User management page."""
    return render_template("admin/users.html")


@bp.route("/users/<int:user_id>", methods=["GET"])
@login_required
@admin_required
def get_user(user_id: int):
    result = AdminService.get_user_detail(user_id)
    if not result:
        return jsonify({"error": "User not found"}), 404
    return jsonify(result), 200


@bp.route("/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_user(user_id: int):
    """Deletes a user account."""
    if user_id == current_user.id:
        return jsonify({"error": "Cannot delete yourself"}), 400
    result = AdminService.delete_user(user_id)
    return jsonify(result), 200


@bp.route("/users/<int:user_id>/ban", methods=["POST"])
@login_required
@admin_required
def ban_user(user_id: int):
    if user_id == current_user.id:
        return jsonify({"error": "Cannot ban yourself"}), 400
    result = AdminService.ban_user(user_id)
    return jsonify(result), 200


@bp.route("/users/<int:user_id>/unban", methods=["POST"])
@login_required
@admin_required
def unban_user(user_id: int):
    result = AdminService.unban_user(user_id)
    return jsonify(result), 200


@bp.route("/users/<int:user_id>/role", methods=["POST"])
@login_required
@admin_required
def change_role(user_id: int):
    data = request.get_json() or {}
    role = data.get("role", "")
    if role not in ("user", "recruiter", "admin"):
        return jsonify({"error": "Invalid role"}), 400
    if user_id == current_user.id:
        return jsonify({"error": "Cannot change own role"}), 400
    result = AdminService.change_user_role(user_id, role)
    return jsonify(result), 200


@bp.route("/activity-logs", methods=["GET"])
@login_required
@admin_required
def activity_logs_api():
    page = request.args.get("page", 1, type=int)
    action = request.args.get("action", "")
    result = AdminService.get_activity_logs(page, action)
    return jsonify(result), 200


@bp.route("/activity-logs/view", methods=["GET"])
@login_required
@admin_required
def view_logs():
    """System activity logs page."""
    return render_template("admin/logs.html")


@bp.route("/stats", methods=["GET"])
@login_required
@admin_required
def system_stats():
    result = AdminService.get_system_stats()
    return jsonify(result), 200


@bp.route("/jobs", methods=["GET"])
@login_required
@admin_required
def manage_jobs():
    """Job management page."""
    return render_template("admin/jobs.html")


@bp.route("/jobs", methods=["POST"])
@login_required
@admin_required
def create_job():
    data = request.get_json() or {}
    result = AdminService.create_job(data)
    return jsonify(result), 201


@bp.route("/jobs/<int:job_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_job(job_id: int):
    result = AdminService.delete_job(job_id)
    return jsonify(result), 200


# ── Safe Stats Helper ──
def _safe_stats() -> dict:
    """Fetch dashboard stats safely. Returns empty defaults on any error."""
    try:
        return AdminService.get_dashboard_stats()
    except Exception:
        return {
            "total_users": 0,
            "premium_users": 0,
            "recruiters": 0,
            "resumes_uploaded": 0,
            "jobs_posted": 0,
            "payments_total": 0,
            "today_signups": 0,
        }