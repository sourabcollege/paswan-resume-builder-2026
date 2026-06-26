from __future__ import annotations
import pytest
from app.utils.offline_engines import (
    ATSScoringEngine,
    SkillExtractionEngine,
    KeywordMatchingEngine,
    JobMatchEngine,
    SkillGapAnalysisEngine,
    ResumeCompletenessScorer,
)


# ── Fixtures ────────────────────────────────────────────────────────
@pytest.fixture
def sample_resume():
    return {
        "raw_text": (
            "John Doe\njohn@email.com\n"
            "Experience: Software Engineer at Google 2020-2023\n"
            "Skills: Python, Flask, Docker, PostgreSQL, Redis\n"
            "Education: B.Tech Computer Science 2020\n"
            "Projects: Resume Builder SaaS application\n"
            "Certifications: AWS Certified Developer"
        ),
        "name": "John Doe",
        "email": "john@email.com",
        "skills": ["Python", "Flask", "Docker", "PostgreSQL", "Redis"],
        "experience": [
            {
                "title": "Software Engineer",
                "company": "Google",
                "duration": "2020-2023",
            }
        ],
        "education": [
            {
                "degree": "B.Tech Computer Science",
                "year": "2020",
            }
        ],
        "projects": ["Resume Builder SaaS application"],
        "certifications": ["AWS Certified Developer"],
        "summary": "Experienced software engineer.",
    }


@pytest.fixture
def empty_resume():
    return {}


@pytest.fixture
def sample_job():
    return {
        "title": "Backend Engineer",
        "required_skills": "Python, Flask, Docker, PostgreSQL, AWS",
        "description": (
            "We need Python Flask Docker PostgreSQL AWS Redis "
            "experience for backend development role."
        ),
    }


# ── ATS Scoring Engine ───────────────────────────────────────────────
class TestATSScoringEngine:

    def test_score_returns_obj(self, sample_resume):
        result = ATSScoringEngine().analyze(sample_resume["raw_text"])
        assert hasattr(result, "score")

    def test_score_has_total(self, sample_resume):
        result = ATSScoringEngine().analyze(sample_resume["raw_text"])
        assert hasattr(result, "score")

    def test_score_range(self, sample_resume):
        result = ATSScoringEngine().analyze(sample_resume["raw_text"])
        assert 0 <= result.score <= 100

    def test_empty_input_no_crash(self, empty_resume):
        result = ATSScoringEngine().analyze("")
        assert result.score == 0.0

    def test_full_resume_high_score(self, sample_resume):
        result = ATSScoringEngine().analyze(sample_resume["raw_text"])
        assert result.score > 40

    def test_score_has_breakdown(self, sample_resume):
        result = ATSScoringEngine().analyze(sample_resume["raw_text"])
        assert hasattr(result, "breakdown")


# ── Skill Extraction Engine ──────────────────────────────────────────
class TestSkillExtractionEngine:

    def test_extract_returns_obj(self, sample_resume):
        result = SkillExtractionEngine().extract(
            sample_resume["raw_text"]
        )
        assert hasattr(result, "skills")

    def test_extract_finds_python(self, sample_resume):
        result = SkillExtractionEngine().extract(
            sample_resume["raw_text"]
        )
        all_skills = result.skills
        assert any(
            "python" in s.lower() for s in all_skills
        )

    def test_empty_text_no_crash(self):
        result = SkillExtractionEngine().extract("")
        assert hasattr(result, "skills")

    def test_has_categorized_skills(self, sample_resume):
        result = SkillExtractionEngine().extract(
            sample_resume["raw_text"]
        )
        assert hasattr(result, "skills_by_category")


# ── Keyword Matching Engine ──────────────────────────────────────────
class TestKeywordMatchingEngine:

    def test_match_returns_obj(self, sample_resume, sample_job):
        result = KeywordMatchingEngine().match(
            sample_resume["raw_text"],
            sample_job["description"],
        )
        assert hasattr(result, "score")

    def test_match_has_score(self, sample_resume, sample_job):
        result = KeywordMatchingEngine().match(
            sample_resume["raw_text"],
            sample_job["description"],
        )
        assert hasattr(result, "score")

    def test_empty_inputs_no_crash(self):
        result = KeywordMatchingEngine().match("", "")
        assert result.score == 0.0

    def test_score_range(self, sample_resume, sample_job):
        result = KeywordMatchingEngine().match(
            sample_resume["raw_text"],
            sample_job["description"],
        )
        assert 0 <= result.score <= 100


# ── Job Match Engine ─────────────────────────────────────────────────
class TestJobMatchEngine:

    def test_match_returns_obj(self, sample_resume, sample_job):
        result = JobMatchEngine().match(sample_resume["raw_text"], sample_job["description"])
        assert hasattr(result, "score")

    def test_match_has_score(self, sample_resume, sample_job):
        result = JobMatchEngine().match(sample_resume["raw_text"], sample_job["description"])
        assert hasattr(result, "score")

    def test_score_range(self, sample_resume, sample_job):
        result = JobMatchEngine().match(sample_resume["raw_text"], sample_job["description"])
        assert 0 <= result.score <= 100

    def test_empty_resume_no_crash(self, empty_resume, sample_job):
        result = JobMatchEngine().match("", sample_job["description"])
        assert result.score >= 0.0

    def test_good_match_high_score(self, sample_resume, sample_job):
        result = JobMatchEngine().match(sample_resume["raw_text"], sample_job["description"])
        assert result.score > 40


# ── Skill Gap Analysis Engine ────────────────────────────────────────
class TestSkillGapAnalysisEngine:

    def test_gap_returns_obj(self, sample_resume, sample_job):
        result = SkillGapAnalysisEngine().analyze(
            sample_resume["skills"], sample_job["required_skills"].split(", ")
        )
        assert hasattr(result, "missing_skills")

    def test_gap_has_missing_skills(self, sample_resume, sample_job):
        result = SkillGapAnalysisEngine().analyze(
            sample_resume["skills"], sample_job["required_skills"].split(", ")
        )
        assert hasattr(result, "missing_skills")

    def test_empty_resume_no_crash(self, empty_resume, sample_job):
        result = SkillGapAnalysisEngine().analyze(
            [], sample_job["required_skills"].split(", ")
        )
        assert hasattr(result, "missing_skills")

    def test_perfect_match_no_gap(self):
        resume_skills = ["Python", "Flask", "Docker", "PostgreSQL", "AWS"]
        required_skills = ["Python", "Flask", "Docker", "PostgreSQL", "AWS"]

        result = SkillGapAnalysisEngine().analyze(resume_skills, required_skills)
        assert len(result.missing_skills) == 0


# ── Resume Completeness Scorer ───────────────────────────────────────
class TestResumeCompletenessScorer:

    def test_score_returns_obj(self, sample_resume):
        result = ResumeCompletenessScorer().score(sample_resume["raw_text"])
        assert hasattr(result, "score")

    def test_score_has_percentage(self, sample_resume):
        result = ResumeCompletenessScorer().score(sample_resume["raw_text"])
        assert hasattr(result, "score")

    def test_full_resume_high_score(self, sample_resume):
        # We pass the full dict which has parsed sections as well
        result = ResumeCompletenessScorer().score(sample_resume)
        assert result.score > 40

    def test_empty_resume_zero(self, empty_resume):
        result = ResumeCompletenessScorer().score("")
        assert result.score == 0.0

    def test_score_range(self, sample_resume):
        result = ResumeCompletenessScorer().score(sample_resume["raw_text"])
        assert 0 <= result.score <= 100
