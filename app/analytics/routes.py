from __future__ import annotations

from app.analytics import bp
from flask import jsonify, request, render_template
from flask_login import login_required, current_user
from app.services.analytics_service import AnalyticsService


@bp.route("/", methods=["GET"])
@login_required
def overview():
    """Main analytics dashboard page."""
    dashboard_data = AnalyticsService.get_dashboard_data(current_user.id)

    # Normalize data for template with safe defaults
    template_data = {
        "avg_ats_score": dashboard_data.get("avg_ats_score") if isinstance(dashboard_data, dict) else 0,
        "best_score": dashboard_data.get("best_score") if isinstance(dashboard_data, dict) else 0,
        "completeness": dashboard_data.get("completeness") if isinstance(dashboard_data, dict) else 0,
        "job_matches": dashboard_data.get("job_matches") if isinstance(dashboard_data, dict) else 0,
        "resume_count": dashboard_data.get("resume_count") if isinstance(dashboard_data, dict) else 0,
        "ats_trend": dashboard_data.get("ats_trend") if isinstance(dashboard_data, dict) else [],
        "skills_breakdown": dashboard_data.get("skills_breakdown") if isinstance(dashboard_data, dict) else [],
        "recent_activity": dashboard_data.get("recent_activity") if isinstance(dashboard_data, dict) else [],
    }
    return render_template("analytics/overview.html", **template_data)


@bp.route("/dashboard", methods=["GET"])
@login_required
def dashboard():
    data = AnalyticsService.get_dashboard_data(current_user.id)
    return jsonify(data), 200


@bp.route("/ats-trend", methods=["GET"])
@login_required
def ats_trend():
    resume_id = request.args.get("resume_id", type=int)
    data = AnalyticsService.get_ats_trend(current_user.id, resume_id)
    return jsonify(data), 200


@bp.route("/skill-breakdown", methods=["GET"])
@login_required
def skill_breakdown():
    data = AnalyticsService.get_skill_breakdown(current_user.id)
    return jsonify(data), 200


@bp.route("/job-match-trend", methods=["GET"])
@login_required
def job_match_trend():
    data = AnalyticsService.get_job_match_trend(current_user.id)
    return jsonify(data), 200


@bp.route("/completeness", methods=["GET"])
@login_required
def completeness():
    resume_id = request.args.get("resume_id", type=int)
    data = AnalyticsService.get_completeness(current_user.id, resume_id)
    return jsonify(data), 200


@bp.route("/activity-timeline", methods=["GET"])
@login_required
def activity_timeline():
    data = AnalyticsService.get_activity_timeline(current_user.id)
    return jsonify(data), 200


@bp.route("/scoring-distribution", methods=["GET"])
@login_required
def scoring_distribution():
    """Returns distribution data of ATS scores for user's resumes."""
    data = AnalyticsService.get_scoring_distribution(current_user.id)
    return jsonify(data), 200


@bp.route("/skill-gap-distribution", methods=["GET"])
@login_required
def skill_gap_distribution():
    """Returns aggregated data about missing skills across job matches."""
    data = AnalyticsService.get_skill_gap_distribution(current_user.id)
    return jsonify(data), 200