from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

import requests

from flask import current_app

from app.extensions import db
from app.models.activity import ActivityLog
from app.models.job import Job, JobMatch
from app.models.resume import Resume, ResumeVersion
from app.models.user import User
from app.repositories.jobs import JobRepository
from app.repositories.resumes import ResumeRepository
from app.utils.offline_engines import JobMatchEngine, SkillGapAnalysisEngine


TOP_RECOMMENDATION_LIMIT = 5
USER_TRACKING_STATUSES = {"saved", "applied", "hidden"}


# ═══════════════════════════════════════════════════════════════
# 🌐 EXTERNAL JOB CACHE (In-memory for development)
# Key: adzuna_raw_id (without prefix), Value: normalized job dict
# ═══════════════════════════════════════════════════════════════
_external_jobs_cache: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class JobServiceResult:
    success: bool
    message: str
    status_code: int = 200
    data: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, list[str]] = field(default_factory=dict)


class JobService:
    def __init__(
        self,
        jobs: JobRepository | None = None,
        resumes: ResumeRepository | None = None,
        match_engine: JobMatchEngine | None = None,
        gap_engine: SkillGapAnalysisEngine | None = None,
    ) -> None:
        self.jobs = jobs or JobRepository()
        self.resumes = resumes or ResumeRepository()
        self.match_engine = match_engine or JobMatchEngine()
        self.gap_engine = gap_engine or SkillGapAnalysisEngine()

    def list_jobs(self, user: User, filters: Mapping[str, Any]) -> JobServiceResult:
        limit = min(max(_safe_int(filters.get("limit"), 50), 1), 100)
        offset = max(_safe_int(filters.get("offset"), 0), 0)
        
        # Try local DB first
        local_jobs = self.jobs.list_visible_for_user(
            user.id,
            user.role,
            search=_optional_string(filters.get("q")),
            location=_optional_string(filters.get("location")),
            experience_level=_optional_string(filters.get("experience_level")),
            workplace_type=_optional_string(filters.get("workplace_type")),
            employment_type=_optional_string(filters.get("employment_type")),
            limit=limit,
            offset=offset,
        )
        
        # If local jobs found, return them
        if local_jobs:
            return JobServiceResult(
                True,
                "Jobs loaded.",
                data={"jobs": [serialize_job(job) for job in local_jobs], "limit": limit, "offset": offset},
            )
        
        # Fallback: Fetch from Adzuna API
        external_jobs = self._fetch_adzuna_jobs(filters)
        
        if external_jobs:
            return JobServiceResult(
                True,
                f"Found {len(external_jobs)} jobs from external sources.",
                data={"jobs": external_jobs, "limit": limit, "offset": offset, "source": "external"},
            )
        
        return JobServiceResult(
            True,
            "No jobs found.",
            data={"jobs": [], "limit": limit, "offset": offset},
        )

    def _fetch_adzuna_jobs(self, filters: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Fetch jobs from Adzuna API when local DB is empty."""
        app_id = current_app.config.get("ADZUNA_APP_ID")
        app_key = current_app.config.get("ADZUNA_APP_KEY")
        country = current_app.config.get("ADZUNA_COUNTRY", "in")
        max_results = current_app.config.get("ADZUNA_MAX_RESULTS", 20)
        
        if not app_id or not app_key:
            return []
        
        try:
            url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
            
            # Build query
            query = _optional_string(filters.get("q")) or "software developer"
            location = _optional_string(filters.get("location"))
            
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "what": query,
                "max_days_old": 30,
                "results_per_page": max_results,
            }
            
            if location:
                params["where"] = location
            
            # Experience level mapping
            experience_level = _optional_string(filters.get("experience_level"))
            if experience_level:
                salary_min = self._get_min_salary_for_exp(experience_level)
                if salary_min > 0:
                    params["salary_min"] = salary_min
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            jobs = []
            for result in data.get("results", []):
                job = self._normalize_adzuna_job(result)
                jobs.append(job)
                
                # ═══════════════════════════════════════════════════
                # 🔥 CACHE POPULATE: Store in global cache
                # ═══════════════════════════════════════════════════
                raw_adzuna_id = str(result.get("id", ""))
                if raw_adzuna_id:
                    _external_jobs_cache[raw_adzuna_id] = job
                    current_app.logger.debug(f"Cached Adzuna job: {raw_adzuna_id}")
            
            return jobs
            
        except Exception as e:
            current_app.logger.error(f"Adzuna API error: {e}")
            return []

    def _get_min_salary_for_exp(self, experience_level: str) -> int:
        """Map experience level to minimum salary for Adzuna filtering."""
        salary_map = {
            "entry": 200000,      # 2L
            "junior": 400000,     # 4L
            "mid": 800000,        # 8L
            "senior": 1500000,    # 15L
            "lead": 2500000,      # 25L
            "executive": 5000000, # 50L
        }
        return salary_map.get(experience_level, 0)

    def _normalize_adzuna_job(self, result: dict[str, Any]) -> dict[str, Any]:
        """Convert Adzuna API response to internal job schema."""
        salary_min = result.get("salary_min")
        salary_max = result.get("salary_max")
        
        # Convert to cents if available
        salary_min_cents = int(salary_min * 100) if salary_min else None
        salary_max_cents = int(salary_max * 100) if salary_max else None
        
        # Extract skills from title and description
        title = result.get("title", "")
        description = result.get("description", "")
        skills = self._extract_skills_from_text(f"{title} {description}")
        
        # Map workplace type
        workplace_type = "remote" if "remote" in description.lower() else "onsite"
        
        # Map employment type
        contract_type = result.get("contract_type", "")
        employment_map = {
            "permanent": "full_time",
            "contract": "contract",
            "part_time": "part_time",
            "temporary": "contract",
        }
        employment_type = employment_map.get(contract_type, "full_time")
        
        # Map experience level from salary
        salary = salary_max or salary_min or 0
        if salary >= 2000000:
            experience_level = "senior"
        elif salary >= 800000:
            experience_level = "mid"
        elif salary >= 400000:
            experience_level = "junior"
        else:
            experience_level = "entry"
        
        return {
            "id": f"adzuna_{result.get('id', 'unknown')}",
            "title": title,
            "company_name": result.get("company", {}).get("display_name", "Unknown Company"),
            "location": result.get("location", {}).get("display_name", "India"),
            "workplace_type": workplace_type,
            "employment_type": employment_type,
            "experience_level": experience_level,
            "description": description,
            "responsibilities": None,
            "requirements": description,
            "required_skills": skills,
            "preferred_skills": [],
            "salary_min_cents": salary_min_cents,
            "salary_max_cents": salary_max_cents,
            "salary_currency": "INR",
            "external_url": result.get("redirect_url", ""),
            "published_at": result.get("created_at"),
            "expires_at": None,
            "source": "adzuna",
        }

    def _extract_skills_from_text(self, text: str) -> list[str]:
        """Extract common tech skills from job text."""
        common_skills = {
            "python", "javascript", "java", "c++", "c#", "go", "rust", "ruby", "php",
            "typescript", "swift", "kotlin", "scala", "perl", "r", "matlab",
            "react", "angular", "vue", "svelte", "next.js", "nuxt.js",
            "node.js", "express", "django", "flask", "fastapi", "spring",
            "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
            "aws", "azure", "gcp", "docker", "kubernetes", "jenkins", "gitlab",
            "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
            "html", "css", "sass", "less", "bootstrap", "tailwind",
            "git", "github", "gitlab", "bitbucket", "jira", "confluence",
            "linux", "ubuntu", "centos", "windows", "macos",
            "agile", "scrum", "kanban", "devops", "ci/cd",
            "machine learning", "deep learning", "ai", "data science",
            "blockchain", "ethereum", "solidity", "smart contracts",
            "android", "ios", "flutter", "react native", "xamarin",
            "tableau", "power bi", "excel", "spss",
            "hadoop", "spark", "kafka", "airflow",
            "terraform", "ansible", "puppet", "chef",
            "prometheus", "grafana", "elk", "splunk",
        }
        
        text_lower = text.lower()
        found_skills = []
        
        for skill in common_skills:
            if skill in text_lower:
                found_skills.append(skill.title() if " " not in skill else skill.title())
        
        return found_skills[:10]  # Limit to top 10

    def get_job(self, user: User, public_id: str) -> JobServiceResult:
        # Check if it's an external job (Adzuna)
        if public_id.startswith("adzuna_"):
            return self._get_external_job(public_id)
        
        job = self.jobs.get_visible_by_public_id(public_id, user.id, user.role)
        if job is None:
            return JobServiceResult(False, "Job not found.", status_code=404)
        return JobServiceResult(True, "Job loaded.", data={"job": serialize_job(job)})

    def _get_external_job(self, public_id: str) -> JobServiceResult:
        """Fetch single external job from cache FIRST, then API fallback."""
        adzuna_id = public_id.replace("adzuna_", "")
        
        # ═══════════════════════════════════════════════════════════
        # 🔥 STEP 1: CHECK CACHE FIRST
        # ═══════════════════════════════════════════════════════════
        if adzuna_id in _external_jobs_cache:
            current_app.logger.debug(f"Cache HIT for Adzuna job: {adzuna_id}")
            return JobServiceResult(
                True,
                "Job loaded from cache.",
                data={"job": _external_jobs_cache[adzuna_id]},
            )
        
        current_app.logger.debug(f"Cache MISS for Adzuna job: {adzuna_id}")
        
        # ═══════════════════════════════════════════════════════════
        # STEP 2: CACHE MISS — Try API fallback (rare)
        # ═══════════════════════════════════════════════════════════
        app_id = current_app.config.get("ADZUNA_APP_ID")
        app_key = current_app.config.get("ADZUNA_APP_KEY")
        country = current_app.config.get("ADZUNA_COUNTRY", "in")
        
        if not app_id or not app_key:
            return JobServiceResult(False, "External job service not configured.", status_code=503)
        
        try:
            # Search with job ID as keyword (best effort fallback)
            url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "what": adzuna_id,
                "results_per_page": 10,
            }
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            for result in data.get("results", []):
                if str(result.get("id")) == adzuna_id:
                    job = self._normalize_adzuna_job(result)
                    # Cache it for future
                    _external_jobs_cache[adzuna_id] = job
                    return JobServiceResult(True, "Job loaded.", data={"job": job})
            
            return JobServiceResult(False, "Job not found.", status_code=404)
            
        except Exception as e:
            current_app.logger.error(f"Adzuna API error (detail fallback): {e}")
            return JobServiceResult(False, "Failed to load external job.", status_code=503)

    def match_job(
        self,
        user: User,
        job_public_id: str,
        resume_public_id: str,
        version_public_id: str | None = None,
        *,
        request_meta: dict[str, Any] | None = None,
    ) -> JobServiceResult:
        resolved = self._resolve_context(user, job_public_id, resume_public_id, version_public_id)
        if isinstance(resolved, JobServiceResult):
            return resolved
        job, resume, version = resolved

        match = self._calculate_and_persist(user, job, resume, version)
        self._log_activity(
            user.id,
            "job_match_calculated",
            job=job,
            resume=resume,
            details={"score": match.match_score, "version": version.version_number},
            request_meta=request_meta,
        )
        db.session.commit()
        return JobServiceResult(
            True,
            "Job match calculated.",
            data={"job": serialize_job(job), "match": serialize_job_match(match)},
        )

    def recommend_top_jobs(
        self,
        user: User,
        resume_public_id: str,
        version_public_id: str | None = None,
        *,
        request_meta: dict[str, Any] | None = None,
    ) -> JobServiceResult:
        resume, version = self._resolve_owned_resume(user.id, resume_public_id, version_public_id)
        if resume is None:
            return JobServiceResult(False, "Resume not found.", status_code=404)
        if version is None:
            return JobServiceResult(False, "Create or parse a resume version before requesting recommendations.", status_code=400)

        visible_jobs = self.jobs.list_visible_for_user(user.id, user.role, limit=250)
        
        # If no local jobs, fetch from Adzuna
        if not visible_jobs:
            external_jobs = self._fetch_adzuna_jobs({"q": "software developer"})
            # Create temporary Job objects for matching
            visible_jobs = self._create_temp_jobs_from_external(external_jobs)
        
        self.jobs.clear_recommendation_ranks(user.id, resume.id, version.id)
        matches = [self._calculate_and_persist(user, job, resume, version) for job in visible_jobs]
        matches.sort(key=lambda item: (-item.match_score, item.job_id))
        top_matches = matches[:TOP_RECOMMENDATION_LIMIT]
        for rank, match in enumerate(top_matches, start=1):
            match.recommendation_rank = rank

        self._log_activity(
            user.id,
            "job_recommendations_generated",
            resume=resume,
            details={"candidate_jobs": len(visible_jobs), "recommendation_count": len(top_matches)},
            request_meta=request_meta,
        )
        db.session.commit()
        return JobServiceResult(
            True,
            "Top job recommendations generated.",
            data={
                "resume_id": resume.public_id,
                "version_id": version.public_id,
                "recommendations": [
                    {"job": serialize_job(match.job), "match": serialize_job_match(match)}
                    for match in top_matches
                ],
                "count": len(top_matches),
            },
        )

    def _create_temp_jobs_from_external(self, external_jobs: list[dict[str, Any]]) -> list[Job]:
        """Create temporary Job objects from external API data for matching."""
        temp_jobs = []
        for job_data in external_jobs:
            job = Job(
                public_id=job_data["id"],
                title=job_data["title"],
                company_name=job_data["company_name"],
                slug=job_data["id"],
                location=job_data["location"],
                workplace_type=job_data["workplace_type"],
                employment_type=job_data["employment_type"],
                experience_level=job_data["experience_level"],
                status="published",
                visibility="public",
                description=job_data["description"],
                requirements_text=job_data["requirements"],
                required_skills=job_data["required_skills"],
                preferred_skills=job_data["preferred_skills"],
                salary_min_cents=job_data["salary_min_cents"],
                salary_max_cents=job_data["salary_max_cents"],
                salary_currency=job_data["salary_currency"],
                external_url=job_data["external_url"],
            )
            temp_jobs.append(job)
        return temp_jobs

    def apply_to_job(
        self,
        user: User,
        job_public_id: str,
        resume_public_id: str,
        version_public_id: str | None = None,
        *,
        request_meta: dict[str, Any] | None = None,
    ) -> JobServiceResult:
        # External jobs can't be applied through our system
        if job_public_id.startswith("adzuna_"):
            job_data = self._get_external_job(job_public_id)
            if job_data.success:
                return JobServiceResult(
                    True,
                    "Redirecting to external application.",
                    data={
                        "job": job_data.data["job"],
                        "external_apply_url": job_data.data["job"].get("external_url", ""),
                    },
                )
            return JobServiceResult(False, "External job not found.", status_code=404)
        
        resolved = self._resolve_context(user, job_public_id, resume_public_id, version_public_id)
        if isinstance(resolved, JobServiceResult):
            return resolved
        job, resume, version = resolved
        match = self._calculate_and_persist(user, job, resume, version)
        if match.status in {"shortlisted", "rejected"}:
            return JobServiceResult(False, "This application status can no longer be changed.", status_code=409)

        if match.applied_at is None:
            match.applied_at = _utc_now()
        match.status = "applied"
        self._log_activity(
            user.id,
            "job_application_recorded",
            job=job,
            resume=resume,
            details={"version": version.version_number},
            request_meta=request_meta,
        )
        db.session.commit()
        return JobServiceResult(
            True,
            "Application recorded.",
            data={
                "job": serialize_job(job),
                "match": serialize_job_match(match),
                "external_apply_url": job.external_url,
            },
        )

    def update_tracking_status(
        self,
        user: User,
        job_public_id: str,
        resume_public_id: str,
        status: str,
        version_public_id: str | None = None,
        *,
        request_meta: dict[str, Any] | None = None,
    ) -> JobServiceResult:
        if status not in USER_TRACKING_STATUSES:
            return JobServiceResult(
                False,
                "Unsupported tracking status.",
                status_code=400,
                errors={"status": ["Use saved, applied, or hidden."]},
            )

        # External jobs can't be tracked
        if job_public_id.startswith("adzuna_"):
            return JobServiceResult(False, "Tracking not available for external jobs.", status_code=400)

        resolved = self._resolve_context(user, job_public_id, resume_public_id, version_public_id)
        if isinstance(resolved, JobServiceResult):
            return resolved
        job, resume, version = resolved
        match = self._calculate_and_persist(user, job, resume, version)
        if match.status in {"shortlisted", "rejected"}:
            return JobServiceResult(False, "Recruiter-managed statuses cannot be changed by the candidate.", status_code=409)
        if match.status == "applied" and status != "applied":
            return JobServiceResult(False, "An applied job cannot be moved back to a pre-application status.", status_code=409)

        match.status = status
        if status == "applied" and match.applied_at is None:
            match.applied_at = _utc_now()
        self._log_activity(
            user.id,
            "job_tracking_updated",
            job=job,
            resume=resume,
            details={"status": status, "version": version.version_number},
            request_meta=request_meta,
        )
        db.session.commit()
        return JobServiceResult(True, "Tracking status updated.", data={"match": serialize_job_match(match)})

    def list_tracked_jobs(self, user: User) -> JobServiceResult:
        matches = self.jobs.list_matches_for_user(
            user.id,
            statuses=("saved", "applied", "shortlisted", "rejected", "hidden"),
        )
        return JobServiceResult(
            True,
            "Tracked jobs loaded.",
            data={
                "applications": [
                    {"job": serialize_job(match.job), "match": serialize_job_match(match)}
                    for match in matches
                ]
            },
        )

    def list_jobs_for_page(self, user: User, filters: Mapping[str, Any]) -> JobServiceResult:
        base = self.list_jobs(user, filters)
        if not base.success:
            return base

        resume, version = self._get_latest_resume_context(user.id)
        resume_context = _serialize_resume_context(resume, version)
        job_entries: list[dict[str, Any]] = []
        
        for job_payload in base.data["jobs"]:
            # Check if external job
            if job_payload.get("source") == "adzuna":
                match_preview = None
                if resume is not None and version is not None:
                    match_preview = self._compute_match_preview_external(job_payload, resume, version)
                job_entries.append({"job": job_payload, "match": match_preview})
            else:
                job = self.jobs.get_visible_by_public_id(job_payload["id"], user.id, user.role)
                match_preview = (
                    self._compute_match_preview(job, resume, version)
                    if job is not None and resume is not None and version is not None
                    else None
                )
                job_entries.append({"job": job_payload, "match": match_preview})

        return JobServiceResult(
            True,
            base.message,
            data={
                "jobs": job_entries,
                "resume_context": resume_context,
                "limit": base.data["limit"],
                "offset": base.data["offset"],
                "source": base.data.get("source", "local"),
            },
        )

    def _compute_match_preview_external(self, job_data: dict[str, Any], resume: Resume, version: ResumeVersion) -> dict[str, Any]:
        """Compute match preview for external jobs without DB storage."""
        resume_text = version.plain_text or ""
        user_skills = list(resume.extracted_skills or [])
        
        # Create a temporary job text for matching
        job_text = "\n".join([
            job_data.get("title", ""),
            job_data.get("description", ""),
            job_data.get("requirements", ""),
            " ".join(job_data.get("required_skills", [])),
            " ".join(job_data.get("preferred_skills", [])),
        ])
        
        required_skills = list(job_data.get("required_skills", []))
        preferred_skills = list(job_data.get("preferred_skills", []))

        match_result = self.match_engine.match(
            resume_text,
            job_text,
            user_skills=user_skills,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
        )
        gap_result = self.gap_engine.analyze(
            user_skills,
            required_skills,
            preferred_skills,
            job_text,
        )
        gap_data = gap_result.to_dict()
        return {
            "match_score": match_result.score,
            "skill_score": match_result.skill_score,
            "keyword_score": match_result.keyword_score,
            "experience_score": match_result.experience_score,
            "education_score": match_result.education_score,
            "matched_skills": list(match_result.matched_skills),
            "missing_skills": list(match_result.missing_required_skills + match_result.missing_preferred_skills),
            "missing_required_skills": list(match_result.missing_required_skills),
            "missing_preferred_skills": list(match_result.missing_preferred_skills),
            "priority_gaps": list(gap_data["missing_skills"]),
            "explanation": list(match_result.explanation),
            "scoring_details": {
                "match": match_result.to_dict(),
                "skill_gap": gap_data,
            },
        }

    def get_job_for_page(self, user: User, public_id: str) -> JobServiceResult:
        # External job
        if public_id.startswith("adzuna_"):
            result = self._get_external_job(public_id)
            if not result.success:
                return result
            
            resume, version = self._get_latest_resume_context(user.id)
            resume_context = _serialize_resume_context(resume, version)
            match_preview = None
            if resume is not None and version is not None:
                match_preview = self._compute_match_preview_external(result.data["job"], resume, version)
            
            return JobServiceResult(
                True,
                "Job loaded.",
                data={
                    "job": result.data["job"],
                    "match": match_preview,
                    "resume_context": resume_context,
                    "tracking_status": None,
                },
            )
        
        job = self.jobs.get_visible_by_public_id(public_id, user.id, user.role)
        if job is None:
            return JobServiceResult(False, "Job not found.", status_code=404)

        resume, version = self._get_latest_resume_context(user.id)
        resume_context = _serialize_resume_context(resume, version)
        match_preview = (
            self._compute_match_preview(job, resume, version)
            if resume is not None and version is not None
            else None
        )
        tracking_status = None
        if resume is not None and version is not None:
            persisted = self.jobs.get_match(user.id, job.id, resume.id, version.id)
            tracking_status = persisted.status if persisted else None

        return JobServiceResult(
            True,
            "Job loaded.",
            data={
                "job": serialize_job(job),
                "match": match_preview,
                "resume_context": resume_context,
                "tracking_status": tracking_status,
            },
        )

    def preview_top_recommendations(self, user: User, limit: int = TOP_RECOMMENDATION_LIMIT) -> JobServiceResult:
        resume, version = self._get_latest_resume_context(user.id)
        if resume is None or version is None:
            return JobServiceResult(
                True,
                "Upload a resume to see job recommendations.",
                data={"recommendations": [], "resume_context": None, "count": 0},
            )

        visible_jobs = self.jobs.list_visible_for_user(user.id, user.role, limit=250)
        external_jobs = []
        
        if not visible_jobs:
            external_jobs = self._fetch_adzuna_jobs({"q": "software developer"})
            visible_jobs = self._create_temp_jobs_from_external(external_jobs)
        
        scored: list[tuple[Job, dict[str, Any]]] = []
        for job in visible_jobs:
            scored.append((job, self._compute_match_preview(job, resume, version)))
        scored.sort(key=lambda item: (-item[1]["match_score"], item[0].title.lower()))

        top_entries = scored[: max(min(limit, TOP_RECOMMENDATION_LIMIT), 1)]
        return JobServiceResult(
            True,
            "Top job recommendations loaded.",
            data={
                "recommendations": [
                    {"job": serialize_job(job), "match": match_preview}
                    for job, match_preview in top_entries
                ],
                "resume_context": _serialize_resume_context(resume, version),
                "count": len(top_entries),
            },
        )

    def _resolve_context(
        self,
        user: User,
        job_public_id: str,
        resume_public_id: str,
        version_public_id: str | None,
    ) -> tuple[Job, Resume, ResumeVersion] | JobServiceResult:
        job = self.jobs.get_visible_by_public_id(job_public_id, user.id, user.role)
        if job is None:
            return JobServiceResult(False, "Job not found.", status_code=404)
        resume, version = self._resolve_owned_resume(user.id, resume_public_id, version_public_id)
        if resume is None:
            return JobServiceResult(False, "Resume not found.", status_code=404)
        if version is None:
            return JobServiceResult(False, "Resume version not found.", status_code=404)
        return job, resume, version

    def _get_latest_resume_context(self, user_id: int) -> tuple[Resume | None, ResumeVersion | None]:
        resumes = self.resumes.list_for_user(user_id)
        if not resumes:
            return None, None
        resume = resumes[0]
        version = self.resumes.get_current_version(resume.id, user_id)
        return resume, version

    def _compute_match_preview(self, job: Job, resume: Resume, version: ResumeVersion) -> dict[str, Any]:
        resume_text = version.plain_text or ""
        user_skills = list(resume.extracted_skills or [])
        job_text = _job_text(job)
        required_skills = list(job.required_skills or [])
        preferred_skills = list(job.preferred_skills or [])

        match_result = self.match_engine.match(
            resume_text,
            job_text,
            user_skills=user_skills,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
        )
        gap_result = self.gap_engine.analyze(
            user_skills,
            required_skills,
            preferred_skills,
            job_text,
        )
        gap_data = gap_result.to_dict()
        return {
            "match_score": match_result.score,
            "skill_score": match_result.skill_score,
            "keyword_score": match_result.keyword_score,
            "experience_score": match_result.experience_score,
            "education_score": match_result.education_score,
            "matched_skills": list(match_result.matched_skills),
            "missing_skills": list(match_result.missing_required_skills + match_result.missing_preferred_skills),
            "missing_required_skills": list(match_result.missing_required_skills),
            "missing_preferred_skills": list(match_result.missing_preferred_skills),
            "priority_gaps": list(gap_data["missing_skills"]),
            "explanation": list(match_result.explanation),
            "scoring_details": {
                "match": match_result.to_dict(),
                "skill_gap": gap_data,
            },
        }

    def _resolve_owned_resume(
        self,
        user_id: int,
        resume_public_id: str,
        version_public_id: str | None,
    ) -> tuple[Resume | None, ResumeVersion | None]:
        resume = self.resumes.get_by_public_id_for_user(resume_public_id, user_id)
        if resume is None:
            return None, None
        version = (
            self.resumes.get_version_by_public_id_for_user(version_public_id, user_id)
            if version_public_id
            else self.resumes.get_current_version(resume.id, user_id)
        )
        if version is not None and version.resume_id != resume.id:
            return resume, None
        return resume, version

    def _calculate_and_persist(self, user: User, job: Job, resume: Resume, version: ResumeVersion) -> JobMatch:
        resume_text = version.plain_text or ""
        user_skills = list(resume.extracted_skills or [])
        job_text = _job_text(job)
        required_skills = list(job.required_skills or [])
        preferred_skills = list(job.preferred_skills or [])

        match_result = self.match_engine.match(
            resume_text,
            job_text,
            user_skills=user_skills,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
        )
        gap_result = self.gap_engine.analyze(
            user_skills,
            required_skills,
            preferred_skills,
            job_text,
        )
        match = self.jobs.get_match(user.id, job.id, resume.id, version.id)
        if match is None:
            match = JobMatch(
                user_id=user.id,
                resume_id=resume.id,
                version_id=version.id,
                job_id=job.id,
                status="recommended",
            )
            self.jobs.add_match(match)

        gap_data = gap_result.to_dict()
        match.match_score = match_result.score
        match.skill_score = match_result.skill_score
        match.keyword_score = match_result.keyword_score
        match.experience_score = match_result.experience_score
        match.education_score = match_result.education_score
        match.matched_skills = list(match_result.matched_skills)
        match.missing_skills = list(match_result.missing_required_skills + match_result.missing_preferred_skills)
        match.priority_gaps = list(gap_data["missing_skills"])
        match.scoring_details = {
            "match": match_result.to_dict(),
            "skill_gap": gap_data,
        }
        match.explanation = "\n".join(match_result.explanation)
        match.last_calculated_at = _utc_now()
        return match

    def _log_activity(
        self,
        user_id: int,
        event_type: str,
        *,
        job: Job | None = None,
        resume: Resume | None = None,
        details: dict[str, Any] | None = None,
        request_meta: dict[str, Any] | None = None,
    ) -> None:
        request_meta = request_meta or {}
        db.session.add(
            ActivityLog(
                actor_user_id=user_id,
                target_user_id=user_id,
                resume_id=resume.id if resume else None,
                job_id=job.id if job else None,
                category="job",
                event_type=event_type,
                severity="info",
                status="success",
                request_id=request_meta.get("request_id"),
                remote_addr_hash=request_meta.get("remote_addr_hash"),
                user_agent_hash=request_meta.get("user_agent_hash"),
                details=details or {},
            )
        )


def serialize_job(job: Job | dict[str, Any]) -> dict[str, Any]:
    """Serialize a Job model OR external job dict to consistent format."""
    if isinstance(job, dict):
        return job
    return {
        "id": job.public_id,
        "title": job.title,
        "company_name": job.company_name,
        "location": job.location,
        "workplace_type": job.workplace_type,
        "employment_type": job.employment_type,
        "experience_level": job.experience_level,
        "description": job.description,
        "responsibilities": job.responsibilities,
        "requirements": job.requirements_text,
        "required_skills": list(job.required_skills or []),
        "preferred_skills": list(job.preferred_skills or []),
        "salary_min_cents": job.salary_min_cents,
        "salary_max_cents": job.salary_max_cents,
        "salary_currency": job.salary_currency,
        "external_url": job.external_url,
        "published_at": _iso(job.published_at),
        "expires_at": _iso(job.expires_at),
        "source": "local",
    }


def _serialize_resume_context(resume: Resume | None, version: ResumeVersion | None) -> dict[str, Any] | None:
    if resume is None or version is None:
        return None
    return {
        "resume_id": resume.public_id,
        "version_id": version.public_id,
        "title": resume.title,
    }


def serialize_job_match(match: JobMatch) -> dict[str, Any]:
    return {
        "job_id": match.job.public_id if match.job else None,
        "resume_id": match.resume.public_id if match.resume else None,
        "version_id": match.version.public_id if match.version else None,
        "match_score": match.match_score,
        "skill_score": match.skill_score,
        "keyword_score": match.keyword_score,
        "experience_score": match.experience_score,
        "education_score": match.education_score,
        "status": match.status,
        "recommendation_rank": match.recommendation_rank,
        "matched_skills": list(match.matched_skills or []),
        "missing_skills": list(match.missing_skills or []),
        "priority_gaps": list(match.priority_gaps or []),
        "explanation": match.explanation,
        "applied_at": _iso(match.applied_at),
        "updated_at": _iso(match.updated_at),
    }


def _job_text(job: Job) -> str:
    return "\n".join(
        part
        for part in (
            job.title,
            job.description,
            job.responsibilities,
            job.requirements_text,
            " ".join(job.required_skills or []),
            " ".join(job.preferred_skills or []),
            " ".join(job.keywords or []),
        )
        if part
    )


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_string(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()