from __future__ import annotations

from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import login_required, current_user

from app.ai import bp
from app.services.ai_service import AIService


def _ai_disabled_response():
    return jsonify({"error": "AI features are currently disabled.", "enabled": False}), 503


def _wants_json():
    if request.is_json:
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and request.accept_mimetypes[best] >= request.accept_mimetypes["text/html"]


@bp.route("/rewrite-resume", methods=["GET", "POST"])
@login_required
def rewrite_resume():
    if request.method == "GET":
        from app.models.resume import Resume
        resumes = Resume.query.filter_by(user_id=current_user.id, is_archived=False).order_by(Resume.created_at.desc()).all()
        return render_template("ai/rewrite_resume.html", resumes=resumes)
    
    if not current_app.config.get("AI_ENABLED", False):
        return _ai_disabled_response()
    
    data = request.get_json() or request.form.to_dict()
    resume_id = data.get("resume_id")
    if not resume_id:
        return jsonify({"error": "resume_id required", "rewritten": None}), 400
    
    result = AIService.rewrite_resume(current_user.id, int(resume_id))
    
    if isinstance(result, tuple):
        result = result[0]
    if not isinstance(result, dict):
        result = {"rewritten": str(result), "source": "unknown"}
    if "rewritten" not in result:
        result["rewritten"] = result.get("message", "No content generated")
    
    return jsonify(result), 200


@bp.route("/improve-bullet", methods=["GET", "POST"])
@login_required
def improve_bullet():
    if request.method == "GET":
        return render_template("ai/improve_bullet.html")
    
    if not current_app.config.get("AI_ENABLED", False):
        return _ai_disabled_response()
    
    data = request.get_json() or request.form.to_dict()
    bullet = data.get("bullet", "").strip()
    if not bullet:
        return jsonify({"error": "bullet text required"}), 400
    result = AIService.improve_bullet(bullet)
    return jsonify(result), 200


@bp.route("/generate-summary", methods=["GET", "POST"])
@login_required
def generate_summary():
    if request.method == "GET":
        return render_template("ai/generate_summary.html")
    
    if not current_app.config.get("AI_ENABLED", False):
        return _ai_disabled_response()
    
    data = request.get_json() or request.form.to_dict()
    resume_id = data.get("resume_id")
    if not resume_id:
        return jsonify({"error": "resume_id required"}), 400
    result = AIService.generate_summary(current_user.id, resume_id)
    return jsonify(result), 200


@bp.route("/generate-cover-letter", methods=["GET", "POST"])
@login_required
def generate_cover_letter():
    if request.method == "GET":
        return render_template("ai/generate_cover_letter.html")
    
    if not current_app.config.get("AI_ENABLED", False):
        return _ai_disabled_response()
    
    data = request.get_json() or request.form.to_dict()
    resume_id = data.get("resume_id")
    job_id = data.get("job_id")
    if not resume_id or not job_id:
        return jsonify({"error": "resume_id and job_id required"}), 400
    result = AIService.generate_cover_letter(current_user.id, resume_id, job_id)
    return jsonify(result), 200


@bp.route("/interview-prep", methods=["GET", "POST"])
@login_required
def interview_prep():
    if request.method == "GET":
        return render_template("ai/interview_prep.html")
    
    if not current_app.config.get("AI_ENABLED", False):
        return _ai_disabled_response()
    
    data = request.get_json() or request.form.to_dict()
    resume_id = data.get("resume_id")
    job_id = data.get("job_id")
    if not resume_id or not job_id:
        return jsonify({"error": "resume_id and job_id required"}), 400
    result = AIService.generate_interview_prep(current_user.id, resume_id, job_id)
    return jsonify(result), 200


@bp.route("/skill-optimization", methods=["GET", "POST"])
@login_required
def skill_optimization():
    if request.method == "GET":
        return render_template("ai/skill_optimization.html")
    
    if not current_app.config.get("AI_ENABLED", False):
        return _ai_disabled_response()
    
    data = request.get_json() or request.form.to_dict()
    resume_id = data.get("resume_id")
    job_id = data.get("job_id")
    if not resume_id or not job_id:
        return jsonify({"error": "resume_id and job_id required"}), 400
    result = AIService.suggest_skill_optimization(current_user.id, resume_id, job_id)
    return jsonify(result), 200


@bp.route("/status/<int:task_id>", methods=["GET"])
@login_required
def task_status(task_id: int):
    result = AIService.get_task_status(current_user.id, task_id)
    return jsonify(result), 200