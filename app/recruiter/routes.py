from __future__ import annotations

from app.recruiter import bp
from flask import jsonify, request, render_template
from flask_login import login_required, current_user
from app.recruiter import bp
from app.auth.decorators import recruiter_required
from app.services.recruiter_service import RecruiterService


@bp.route("/", methods=["GET"])
@login_required
@recruiter_required
def dashboard():
    """Recruiter dashboard landing page."""
    return render_template("recruiter/dashboard.html")


@bp.route("/search", methods=["GET"])
@login_required
@recruiter_required
def search_candidates():
    skills = request.args.get("skills", "")
    min_ats = request.args.get("min_ats", 0, type=int)
    max_ats = request.args.get("max_ats", 100, type=int)
    experience = request.args.get("experience", "")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("format") == "json":
        results = RecruiterService.search_candidates(
            skills=skills,
            min_ats=min_ats,
            max_ats=max_ats,
            experience=experience,
        )
        return jsonify(results), 200

    return render_template("recruiter/search.html")


@bp.route("/candidate/<int:user_id>", methods=["GET"])
@login_required
@recruiter_required
def view_candidate(user_id: int):
    result = RecruiterService.get_candidate_profile(user_id)
    if not result:
        return jsonify({"error": "Candidate not found"}), 404

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get("format") == "json":
        return jsonify(result), 200

    return render_template("recruiter/candidate_profile.html", candidate=result)


@bp.route("/shortlist", methods=["POST"])
@login_required
@recruiter_required
def shortlist_candidate():
    data = request.get_json()
    candidate_id = data.get("candidate_id")
    note = data.get("note", "")
    if not candidate_id:
        return jsonify({"error": "candidate_id required"}), 400
    result = RecruiterService.shortlist_candidate(
        recruiter_id=current_user.id,
        candidate_id=candidate_id,
        note=note,
    )
    return jsonify(result), 200


@bp.route("/shortlist", methods=["GET"])
@login_required
@recruiter_required
def get_shortlist():
    result = RecruiterService.get_shortlist(current_user.id)
    return jsonify(result), 200


@bp.route("/shortlist/<int:candidate_id>",
                    methods=["DELETE"])
@login_required
@recruiter_required
def remove_shortlist(candidate_id: int):
    result = RecruiterService.remove_shortlist(
        recruiter_id=current_user.id,
        candidate_id=candidate_id,
    )
    return jsonify(result), 200


@bp.route("/candidate/<int:user_id>/download",
                    methods=["GET"])
@login_required
@recruiter_required
def download_resume(user_id: int):
    result = RecruiterService.get_resume_download_url(user_id)
    if not result:
        return jsonify({"error": "Resume not found"}), 404
    return jsonify(result), 200
