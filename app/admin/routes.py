from __future__ import annotations

from flask import jsonify, request, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from datetime import datetime, timedelta

from app.admin import bp
from app.auth.decorators import admin_required
from app.services.admin_service import AdminService
from app.services.payment_service import PaymentService


# ── DASHBOARD ──
@bp.route("/", methods=["GET"])
@login_required
@admin_required
def dashboard():
    """Admin dashboard landing page."""
    stats = AdminService.get_dashboard_stats()
    return render_template("admin/dashboard.html", stats=stats)


# ── USER MANAGEMENT (HTML Page) ──
@bp.route("/users", methods=["GET"])
@login_required
@admin_required
def users_page():
    """User management page (HTML)."""
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "", type=str)
    role = request.args.get("role", "", type=str)
    status = request.args.get("status", "", type=str)
    result = AdminService.get_all_users(
        page=page,
        per_page=20,
        search=q,
        role=role or None,
        status=status or None,
    )

    # 🆕 Enrich user data with subscription info
    for user in result["users"]:
        sub = PaymentService.get_user_subscription(user["id"])
        user["subscription_plan"] = sub.get("plan", "free")
        user["subscription_status"] = sub.get("status", "active")

    pagination = {
        "page": result["current_page"],
        "pages": result["pages"],
        "prev": result["current_page"] - 1,
        "next": result["current_page"] + 1,
        "total": result["total"],
        "start": (result["current_page"] - 1) * 20 + 1,
        "end": min(result["current_page"] * 20, result["total"]),
        "pages_range": list(range(1, result["pages"] + 1)) if result["pages"] <= 10 else [],
    }
    return render_template(
        "admin/users.html",
        users=result["users"],
        pagination=pagination,
        q=q,
        role=role,
        status=status,
    )


# ── USER MANAGEMENT (JSON API) ──
@bp.route("/api/users", methods=["GET"])
@login_required
@admin_required
def users_api():
    """JSON API for users list."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    search = request.args.get("search", "")
    result = AdminService.get_all_users(page, per_page, search)
    return jsonify(result), 200


@bp.route("/users/<int:user_id>", methods=["GET"])
@login_required
@admin_required
def get_user(user_id: int):
    result = AdminService.get_user_detail(user_id)
    if not result:
        return jsonify({"error": "User not found"}), 404
    return jsonify(result), 200


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id: int):
    if user_id == current_user.id:
        flash("Cannot delete yourself!", "error")
        return redirect(url_for("admin.users_page"))
    result = AdminService.delete_user(user_id, admin_user=current_user)
    if result.get("success"):
        flash("User deleted successfully.", "success")
    else:
        flash(result.get("error", "Failed to delete user."), "error")
    return redirect(url_for("admin.users_page"))


@bp.route("/users/<int:user_id>/ban", methods=["POST"])
@login_required
@admin_required
def ban_user(user_id: int):
    if user_id == current_user.id:
        flash("Cannot ban yourself!", "error")
        return redirect(url_for("admin.users_page"))
    result = AdminService.ban_user(user_id, admin_user=current_user)
    if result.get("success"):
        flash("User banned successfully.", "success")
    else:
        flash(result.get("error", "Failed to ban user."), "error")
    return redirect(url_for("admin.users_page"))


@bp.route("/users/<int:user_id>/unban", methods=["POST"])
@login_required
@admin_required
def unban_user(user_id: int):
    result = AdminService.unban_user(user_id, admin_user=current_user)
    if result.get("success"):
        flash("User unbanned successfully.", "success")
    else:
        flash(result.get("error", "Failed to unban user."), "error")
    return redirect(url_for("admin.users_page"))


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
    result = AdminService.change_user_role(user_id, role, admin_user=current_user)
    return jsonify(result), 200


# ═══════════════════════════════════════════════════════════
# 🆕 NEW: Subscription Management (Admin Only)
# ═══════════════════════════════════════════════════════════
@bp.route("/users/<int:user_id>/activate-pro", methods=["POST"])
@login_required
@admin_required
def activate_user_pro(user_id: int):
    """Manually activate Pro subscription for any user."""
    if user_id == current_user.id:
        flash("Use profile settings to manage your own subscription.", "warning")
        return redirect(url_for("admin.users_page"))

    result = PaymentService.activate_subscription_manually(
        user_id=user_id, plan="pro", admin_user_id=current_user.id
    )
    if result.get("success"):
        flash(f"User upgraded to Pro successfully.", "success")
    else:
        flash(result.get("error", "Failed to activate subscription."), "error")
    return redirect(url_for("admin.users_page"))


@bp.route("/users/<int:user_id>/deactivate-pro", methods=["POST"])
@login_required
@admin_required
def deactivate_user_pro(user_id: int):
    """Deactivate Pro subscription for a user."""
    result = PaymentService.deactivate_subscription(user_id)
    if result.get("success"):
        flash(f"User subscription deactivated.", "success")
    else:
        flash(result.get("error", "Failed to deactivate subscription."), "error")
    return redirect(url_for("admin.users_page"))


# ── RESUME MANAGEMENT (HTML Page) ──
@bp.route("/resumes", methods=["GET"])
@login_required
@admin_required
def resumes_page():
    """Resume management page (HTML)."""
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "", type=str)
    result = AdminService.get_all_resumes(
        page=page, per_page=20, search=q or None
    )
    pagination = {
        "page": result["current_page"],
        "pages": result["pages"],
        "prev": result["current_page"] - 1,
        "next": result["current_page"] + 1,
        "total": result["total"],
        "start": (result["current_page"] - 1) * 20 + 1,
        "end": min(result["current_page"] * 20, result["total"]),
        "pages_range": list(range(1, result["pages"] + 1)) if result["pages"] <= 10 else [],
    }
    return render_template(
        "admin/resumes.html",
        resumes=result["resumes"],
        pagination=pagination,
        q=q,
    )


@bp.route("/resumes/<int:resume_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_resume(resume_id: int):
    result = AdminService.delete_resume(resume_id, admin_user=current_user)
    if result.get("success"):
        flash("Resume deleted successfully.", "success")
    else:
        flash(result.get("error", "Failed to delete resume."), "error")
    return redirect(url_for("admin.resumes_page"))


# ── JOB MANAGEMENT (HTML Page) ──
@bp.route("/jobs", methods=["GET"])
@login_required
@admin_required
def jobs_page():
    """Job management page (HTML)."""
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "", type=str)
    status = request.args.get("status", "", type=str)
    result = AdminService.get_all_jobs(
        page=page, per_page=20, search=q or None
    )
    pagination = {
        "page": result["current_page"],
        "pages": result["pages"],
        "prev": result["current_page"] - 1,
        "next": result["current_page"] + 1,
        "total": result["total"],
        "start": (result["current_page"] - 1) * 20 + 1,
        "end": min(result["current_page"] * 20, result["total"]),
        "pages_range": list(range(1, result["pages"] + 1)) if result["pages"] <= 10 else [],
    }
    return render_template(
        "admin/jobs.html",
        jobs=result["jobs"],
        pagination=pagination,
        q=q,
        status=status,
    )


@bp.route("/jobs", methods=["POST"])
@login_required
@admin_required
def create_job():
    data = request.get_json() or {}
    result = AdminService.create_job(data)
    status = 201 if result.get("success") else 400
    return jsonify(result), status


@bp.route("/jobs/<int:job_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_job(job_id: int):
    result = AdminService.delete_job(job_id, admin_user=current_user)
    if result.get("success"):
        flash("Job deleted successfully.", "success")
    else:
        flash(result.get("error", "Failed to delete job."), "error")
    return redirect(url_for("admin.jobs_page"))


# ── ACTIVITY LOGS (HTML Page) ──
@bp.route("/logs", methods=["GET"])
@login_required
@admin_required
def logs_page():
    """Activity logs page (HTML)."""
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "", type=str)
    entity = request.args.get("entity", "", type=str)
    severity = request.args.get("severity", "", type=str)
    date = request.args.get("date", "", type=str)

    parsed_from = None
    parsed_to = None
    if date:
        try:
            parsed_from = datetime.strptime(date, "%Y-%m-%d")
            parsed_to = parsed_from + timedelta(days=1)
        except ValueError:
            pass

    result = AdminService.get_activity_logs(
        page=page,
        per_page=50,
        action=q,
        entity_type=entity or None,
        date_from=parsed_from,
        date_to=parsed_to,
    )
    pagination = {
        "page": result["current_page"],
        "pages": result["pages"],
        "prev": result["current_page"] - 1,
        "next": result["current_page"] + 1,
        "total": result["total"],
        "start": (result["current_page"] - 1) * 50 + 1,
        "end": min(result["current_page"] * 50, result["total"]),
        "pages_range": list(range(1, result["pages"] + 1)) if result["pages"] <= 10 else [],
    }
    actions_list = AdminService.get_log_actions()

    return render_template(
        "admin/logs.html",
        logs=result["logs"],
        pagination=pagination,
        q=q,
        entity=entity,
        severity=severity,
        date=date,
        actions=actions_list,
    )


# ── ACTIVITY LOGS (JSON API) ──
@bp.route("/api/logs", methods=["GET"])
@login_required
@admin_required
def activity_logs_api():
    """JSON API for activity logs."""
    page = request.args.get("page", 1, type=int)
    action = request.args.get("action", "")
    result = AdminService.get_activity_logs(page, action)
    return jsonify(result), 200


# ── SYSTEM STATS (HTML Page) ──
@bp.route("/stats", methods=["GET"])
@login_required
@admin_required
def stats_page():
    """System statistics page (HTML)."""
    return render_template("admin/stats.html")


# ── SYSTEM STATS (JSON API) ──
@bp.route("/api/stats", methods=["GET"])
@login_required
@admin_required
def system_stats():
    result = AdminService.get_system_stats()
    return jsonify(result), 200