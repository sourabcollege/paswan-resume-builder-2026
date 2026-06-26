from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Sequence


WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-]{1,}")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\s().-]*){8,}\d")
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+\b", re.IGNORECASE)
LINKEDIN_RE = re.compile(r"\blinkedin\.com/in/[a-zA-Z0-9\-_%]+\b", re.IGNORECASE)
GITHUB_RE = re.compile(r"\bgithub\.com/[a-zA-Z0-9\-_%]+\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
DATE_RANGE_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)?\.?\s*(?:19|20)\d{2}\s*(?:-|to)\s*"
    r"(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)?\.?\s*(?:19|20)\d{2}|present|current)\b",
    re.IGNORECASE,
)
DEGREE_RE = re.compile(
    r"\b(?:b\.?tech|m\.?tech|b\.?e\.?|m\.?e\.?|b\.?sc|m\.?sc|bachelor'?s?|master'?s?|ph\.?d|mba|"
    r"diploma|associate degree|computer science|engineering|information technology)\b",
    re.IGNORECASE,
)
CERTIFICATION_RE = re.compile(
    r"\b(?:certified|certification|certificate|aws certified|azure certified|google cloud certified|"
    r"pmp|scrum master|oracle certified|cissp|ceh)\b",
    re.IGNORECASE,
)
QUANTIFIED_IMPACT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:%|percent|x|k|m|ms|s|hours?|days?|users?|requests?|rupees?|usd|inr)\b", re.IGNORECASE)
BULLET_RE = re.compile(r"^\s*(?:[-*+\u2022]|\d+[.)])\s+", re.MULTILINE)
SECTION_HEADING_RE = re.compile(
    r"^\s*(summary|professional summary|objective|skills|technical skills|experience|work experience|"
    r"employment history|education|projects|certifications|certificates|achievements|awards|"
    r"publications|contact|profile)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


STOP_WORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "with",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


ACTION_VERBS = {
    "accelerated",
    "achieved",
    "architected",
    "automated",
    "built",
    "collaborated",
    "created",
    "delivered",
    "designed",
    "developed",
    "deployed",
    "drove",
    "engineered",
    "enhanced",
    "implemented",
    "improved",
    "increased",
    "launched",
    "led",
    "managed",
    "migrated",
    "optimized",
    "reduced",
    "resolved",
    "scaled",
    "shipped",
    "streamlined",
    "tested",
}


SECTION_ALIASES = {
    "contact": ("contact", "profile"),
    "summary": ("summary", "professional summary", "objective"),
    "skills": ("skills", "technical skills"),
    "experience": ("experience", "work experience", "employment history"),
    "education": ("education",),
    "projects": ("projects",),
    "certifications": ("certifications", "certificates"),
    "achievements": ("achievements", "awards", "publications"),
}


SKILL_TAXONOMY: dict[str, dict[str, tuple[str, ...]]] = {
    "programming_languages": {
        "Python": ("python", "python3"),
        "JavaScript": ("javascript", "js", "ecmascript"),
        "TypeScript": ("typescript", "ts"),
        "Java": ("java", "core java"),
        "C": ("c", "c language"),
        "C++": ("c++", "cpp"),
        "C#": ("c#", "c sharp"),
        "Go": ("golang", "go language"),
        "Rust": ("rust",),
        "PHP": ("php",),
        "Ruby": ("ruby",),
        "Kotlin": ("kotlin",),
        "Swift": ("swift",),
        "SQL": ("sql", "structured query language"),
        "R": ("r programming",),
    },
    "frontend": {
        "HTML": ("html", "html5"),
        "CSS": ("css", "css3"),
        "React": ("react", "react.js", "reactjs"),
        "Vue": ("vue", "vue.js", "vuejs"),
        "Angular": ("angular", "angularjs"),
        "Next.js": ("next.js", "nextjs", "next js"),
        "Svelte": ("svelte",),
        "Redux": ("redux", "redux toolkit"),
        "Web Components": ("web components",),
        "Chart.js": ("chart.js", "chartjs", "chart js"),
    },
    "backend": {
        "Flask": ("flask", "flask-restful"),
        "Django": ("django", "django rest framework", "drf"),
        "FastAPI": ("fastapi", "fast api"),
        "Node.js": ("node.js", "nodejs", "node js"),
        "Express": ("express", "express.js"),
        "Spring Boot": ("spring boot",),
        "Laravel": ("laravel",),
        "REST API": ("rest api", "restful api", "restful services"),
        "GraphQL": ("graphql",),
        "Microservices": ("microservices", "microservice architecture"),
    },
    "databases": {
        "PostgreSQL": ("postgresql", "postgres"),
        "MySQL": ("mysql",),
        "SQLite": ("sqlite",),
        "MongoDB": ("mongodb", "mongo"),
        "Redis": ("redis",),
        "Elasticsearch": ("elasticsearch", "elastic search"),
        "SQLAlchemy": ("sqlalchemy", "sql alchemy"),
        "Alembic": ("alembic",),
    },
    "cloud_devops": {
        "Docker": ("docker", "docker compose", "docker-compose"),
        "Kubernetes": ("kubernetes", "k8s"),
        "AWS": ("aws", "amazon web services"),
        "Azure": ("azure", "microsoft azure"),
        "Google Cloud": ("gcp", "google cloud", "google cloud platform"),
        "CI/CD": ("ci/cd", "cicd", "continuous integration", "continuous delivery"),
        "GitHub Actions": ("github actions",),
        "Nginx": ("nginx",),
        "Gunicorn": ("gunicorn",),
        "Linux": ("linux",),
        "Terraform": ("terraform",),
    },
    "data_ai": {
        "Machine Learning": ("machine learning", "ml"),
        "Deep Learning": ("deep learning",),
        "NLP": ("nlp", "natural language processing"),
        "Pandas": ("pandas",),
        "NumPy": ("numpy",),
        "Scikit-learn": ("scikit-learn", "sklearn"),
        "TensorFlow": ("tensorflow",),
        "PyTorch": ("pytorch",),
        "OpenAI API": ("openai api", "openai"),
        "LLM": ("llm", "large language model"),
    },
    "testing_quality": {
        "Pytest": ("pytest",),
        "Unit Testing": ("unit testing", "unit tests"),
        "Integration Testing": ("integration testing", "integration tests"),
        "Selenium": ("selenium",),
        "Playwright": ("playwright",),
        "Jest": ("jest",),
        "Cypress": ("cypress",),
        "TDD": ("tdd", "test driven development"),
    },
    "tools_methods": {
        "Git": ("git", "version control"),
        "Agile": ("agile", "scrum", "kanban"),
        "Jira": ("jira",),
        "Postman": ("postman",),
        "Figma": ("figma",),
        "OAuth": ("oauth", "oauth2"),
        "JWT": ("jwt", "json web token"),
        "RBAC": ("rbac", "role based access control"),
        "Cybersecurity": ("cybersecurity", "security hardening", "application security"),
    },
    "soft_skills": {
        "Leadership": ("leadership", "team leadership"),
        "Communication": ("communication", "stakeholder communication"),
        "Problem Solving": ("problem solving", "analytical thinking"),
        "Mentoring": ("mentoring", "coaching"),
        "Ownership": ("ownership", "accountability"),
    },
}


@dataclass(frozen=True)
class ExtractedSkill:
    name: str
    category: str
    count: int
    confidence: float
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillExtractionResult:
    skills: tuple[str, ...]
    skills_by_category: dict[str, tuple[str, ...]]
    details: tuple[ExtractedSkill, ...]
    confidence_score: float
    evidence: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KeywordMatchResult:
    score: float
    matched_keywords: tuple[str, ...]
    missing_keywords: tuple[str, ...]
    keyword_weights: dict[str, float]
    coverage_ratio: float
    cosine_similarity: float
    suggestions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SkillGap:
    skill: str
    category: str
    priority: str
    priority_score: float
    required: bool
    evidence_count: int
    reason: str


@dataclass(frozen=True)
class SkillGapResult:
    missing_skills: tuple[SkillGap, ...]
    matched_required_skills: tuple[str, ...]
    matched_preferred_skills: tuple[str, ...]
    coverage_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JobMatchResult:
    score: float
    skill_score: float
    keyword_score: float
    experience_score: float
    education_score: float
    matched_skills: tuple[str, ...]
    missing_required_skills: tuple[str, ...]
    missing_preferred_skills: tuple[str, ...]
    explanation: tuple[str, ...]
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SectionCompleteness:
    section: str
    score: float
    weight: float
    present: bool
    suggestions: tuple[str, ...]


@dataclass(frozen=True)
class CompletenessResult:
    score: float
    sections: tuple[SectionCompleteness, ...]
    missing_sections: tuple[str, ...]
    suggestions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ATSScoreResult:
    score: float
    keyword_score: float
    formatting_score: float
    experience_score: float
    skills_score: float
    education_score: float
    breakdown: dict[str, float]
    suggestions: tuple[str, ...]
    matched_keywords: tuple[str, ...]
    missing_keywords: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", str(text))
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
    normalized = normalized.replace("\u2018", "'").replace("\u2019", "'")
    normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def lower_normalized(text: str | None) -> str:
    return normalize_text(text).lower()


def clamp_score(value: float) -> float:
    if math.isnan(value) or value < 0:
        return 0.0
    if value > 100:
        return 100.0
    return round(value, 2)


def tokenize(text: str | None, *, keep_stop_words: bool = False) -> list[str]:
    normalized = lower_normalized(text)
    tokens = [token.strip(".-").lower() for token in WORD_RE.findall(normalized)]
    clean_tokens = [token for token in tokens if len(token) > 1 and (keep_stop_words or token not in STOP_WORDS)]
    return clean_tokens


def term_frequency(tokens: Sequence[str]) -> Counter[str]:
    counts = Counter(tokens)
    total = sum(counts.values()) or 1
    return Counter({term: count / total for term, count in counts.items()})


def cosine_similarity(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    if not left or not right:
        return 0.0
    common_terms = set(left).intersection(right)
    numerator = sum(left[term] * right[term] for term in common_terms)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def canonical_skill_map() -> dict[str, tuple[str, str]]:
    aliases: dict[str, tuple[str, str]] = {}
    for category, skills in SKILL_TAXONOMY.items():
        for canonical, synonyms in skills.items():
            aliases[canonical.lower()] = (canonical, category)
            for synonym in synonyms:
                aliases[synonym.lower()] = (canonical, category)
    return aliases


def skill_category(skill: str) -> str:
    alias_map = canonical_skill_map()
    canonical = lower_normalized(skill)
    if canonical in alias_map:
        return alias_map[canonical][1]
    for category, skills in SKILL_TAXONOMY.items():
        if skill in skills:
            return category
    return "other"


def normalize_skill_name(skill: str) -> str:
    alias_map = canonical_skill_map()
    normalized = lower_normalized(skill)
    if normalized in alias_map:
        return alias_map[normalized][0]
    return " ".join(part.capitalize() if part.isalpha() else part for part in normalized.split())


def unique_preserving_order(items: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = lower_normalized(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(item)
    return tuple(ordered)


def extract_sections(text: str | None) -> dict[str, str]:
    normalized = normalize_text(text)
    if not normalized:
        return {}

    matches = list(SECTION_HEADING_RE.finditer(normalized))
    if not matches:
        return {"body": normalized}

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        heading = lower_normalized(match.group(1))
        canonical = canonical_section_name(heading)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        content = normalized[start:end].strip(" \n:-")
        if content:
            previous = sections.get(canonical, "")
            sections[canonical] = f"{previous}\n{content}".strip() if previous else content

    leading_text = normalized[: matches[0].start()].strip()
    if leading_text:
        sections.setdefault("contact", leading_text)
    return sections


def canonical_section_name(heading: str) -> str:
    normalized = lower_normalized(heading)
    for canonical, aliases in SECTION_ALIASES.items():
        if normalized in aliases:
            return canonical
    return normalized.replace(" ", "_")


class SkillExtractionEngine:
    def __init__(self, taxonomy: Mapping[str, Mapping[str, Sequence[str]]] | None = None) -> None:
        self.taxonomy = taxonomy or SKILL_TAXONOMY
        self._patterns = self._compile_patterns()

    def extract(self, text: str | None, extra_skills: Iterable[str] | None = None) -> SkillExtractionResult:
        normalized = normalize_text(text)
        if not normalized:
            return SkillExtractionResult((), {}, (), 0.0, {})

        skill_counts: Counter[str] = Counter()
        skill_aliases: dict[str, set[str]] = defaultdict(set)
        skill_categories: dict[str, str] = {}
        evidence: dict[str, list[str]] = defaultdict(list)
        searchable = lower_normalized(normalized)

        for canonical, category, alias, pattern in self._patterns:
            matches = list(pattern.finditer(searchable))
            if not matches:
                continue
            skill_counts[canonical] += len(matches)
            skill_aliases[canonical].add(alias)
            skill_categories[canonical] = category
            for match in matches[:3]:
                evidence[canonical].append(_snippet(searchable, match.start(), match.end()))

        for skill in extra_skills or ():
            canonical = normalize_skill_name(skill)
            category = skill_category(canonical)
            pattern = _skill_pattern(lower_normalized(skill))
            matches = list(pattern.finditer(searchable))
            if matches:
                skill_counts[canonical] += len(matches)
                skill_categories[canonical] = category
                skill_aliases[canonical].add(skill)
                for match in matches[:3]:
                    evidence[canonical].append(_snippet(searchable, match.start(), match.end()))

        skills = tuple(skill for skill, _ in skill_counts.most_common())
        grouped: dict[str, list[str]] = defaultdict(list)
        details: list[ExtractedSkill] = []
        total_mentions = sum(skill_counts.values())
        sections = extract_sections(normalized)
        skills_section_bonus = 10 if sections.get("skills") else 0

        for skill in skills:
            category = skill_categories.get(skill, "other")
            grouped[category].append(skill)
            mention_ratio = skill_counts[skill] / max(total_mentions, 1)
            confidence = clamp_score(55 + min(skill_counts[skill], 5) * 6 + mention_ratio * 20 + skills_section_bonus)
            details.append(
                ExtractedSkill(
                    name=skill,
                    category=category,
                    count=skill_counts[skill],
                    confidence=confidence,
                    aliases=tuple(sorted(skill_aliases[skill])),
                )
            )

        category_count = len(grouped)
        confidence_score = clamp_score(min(len(skills), 15) * 4 + category_count * 8 + skills_section_bonus + 20)
        return SkillExtractionResult(
            skills=skills,
            skills_by_category={category: tuple(values) for category, values in grouped.items()},
            details=tuple(details),
            confidence_score=confidence_score if skills else 0.0,
            evidence={skill: tuple(values) for skill, values in evidence.items()},
        )

    def _compile_patterns(self) -> tuple[tuple[str, str, str, re.Pattern[str]], ...]:
        patterns: list[tuple[str, str, str, re.Pattern[str]]] = []
        for category, skills in self.taxonomy.items():
            for canonical, aliases in skills.items():
                for alias in (canonical, *aliases):
                    patterns.append((canonical, category, alias, _skill_pattern(lower_normalized(alias))))
        return tuple(patterns)


class KeywordMatchingEngine:
    def match(
        self,
        resume_text: str | None,
        target_text: str | None,
        required_keywords: Iterable[str] | None = None,
        optional_keywords: Iterable[str] | None = None,
        reference_corpus: Iterable[str] | None = None,
    ) -> KeywordMatchResult:
        resume = normalize_text(resume_text)
        target = normalize_text(target_text)
        required = tuple(normalize_skill_name(keyword) for keyword in required_keywords or ())
        optional = tuple(normalize_skill_name(keyword) for keyword in optional_keywords or ())

        if not resume or not (target or required or optional):
            return KeywordMatchResult(0.0, (), tuple(required + optional), {}, 0.0, 0.0, ("Add a target job description or keyword list.",))

        resume_tokens = tokenize(resume)
        target_tokens = tokenize(" ".join((target, " ".join(required), " ".join(optional))))
        documents = [resume_tokens, target_tokens]
        for document in reference_corpus or ():
            documents.append(tokenize(document))

        idf = _inverse_document_frequency(documents)
        resume_vector = _tfidf_vector(resume_tokens, idf)
        target_vector = _tfidf_vector(target_tokens, idf)
        cosine = cosine_similarity(resume_vector, target_vector)

        keyword_candidates = self._target_keywords(target, required, optional)
        weights = self._keyword_weights(keyword_candidates, target_tokens, idf, set(lower_normalized(k) for k in required))
        matched: list[str] = []
        missing: list[str] = []
        matched_weight = 0.0
        total_weight = sum(weights.values()) or 1.0
        resume_search = lower_normalized(resume)

        for keyword, weight in sorted(weights.items(), key=lambda item: (-item[1], item[0])):
            if _phrase_present(keyword, resume_search):
                matched.append(keyword)
                matched_weight += weight
            else:
                missing.append(keyword)

        coverage_ratio = matched_weight / total_weight
        score = clamp_score((coverage_ratio * 0.75 + cosine * 0.25) * 100)
        suggestions = tuple(f"Add evidence for keyword: {keyword}" for keyword in missing[:8])
        return KeywordMatchResult(
            score=score,
            matched_keywords=tuple(matched),
            missing_keywords=tuple(missing),
            keyword_weights={keyword: round(weight, 4) for keyword, weight in weights.items()},
            coverage_ratio=round(coverage_ratio, 4),
            cosine_similarity=round(cosine, 4),
            suggestions=suggestions,
        )

    def _target_keywords(self, target_text: str, required: Sequence[str], optional: Sequence[str]) -> tuple[str, ...]:
        skills = skill_extraction_engine.extract(target_text, extra_skills=required + optional).skills
        phrase_keywords = _important_phrases(target_text)
        token_keywords = _top_tokens(target_text, limit=25)
        return unique_preserving_order((*required, *optional, *skills, *phrase_keywords, *token_keywords))

    def _keyword_weights(
        self,
        keywords: Sequence[str],
        target_tokens: Sequence[str],
        idf: Mapping[str, float],
        required_set: set[str],
    ) -> dict[str, float]:
        token_counts = Counter(target_tokens)
        weights: dict[str, float] = {}
        for keyword in keywords:
            keyword_lower = lower_normalized(keyword)
            terms = tokenize(keyword_lower)
            if not terms:
                continue
            idf_weight = sum(idf.get(term, 1.0) for term in terms) / len(terms)
            frequency_weight = 1 + sum(token_counts.get(term, 0) for term in terms) / max(len(target_tokens), 1)
            phrase_weight = 1.25 if len(terms) > 1 else 1.0
            required_weight = 1.8 if keyword_lower in required_set else 1.0
            weights[keyword] = idf_weight * frequency_weight * phrase_weight * required_weight
        return weights


class SkillGapAnalysisAlgorithm:
    def analyze(
        self,
        user_skills: Iterable[str] | None,
        required_skills: Iterable[str] | None,
        preferred_skills: Iterable[str] | None = None,
        job_text: str | None = None,
    ) -> SkillGapResult:
        candidate = {lower_normalized(normalize_skill_name(skill)): normalize_skill_name(skill) for skill in user_skills or ()}
        required = unique_preserving_order(normalize_skill_name(skill) for skill in required_skills or ())
        preferred = unique_preserving_order(normalize_skill_name(skill) for skill in preferred_skills or ())

        job_search = lower_normalized(job_text)
        required_missing = [skill for skill in required if lower_normalized(skill) not in candidate]
        preferred_missing = [skill for skill in preferred if lower_normalized(skill) not in candidate]
        matched_required = tuple(skill for skill in required if lower_normalized(skill) in candidate)
        matched_preferred = tuple(skill for skill in preferred if lower_normalized(skill) in candidate)

        gaps = [
            self._build_gap(skill, True, job_search)
            for skill in required_missing
        ] + [
            self._build_gap(skill, False, job_search)
            for skill in preferred_missing
        ]
        gaps.sort(key=lambda gap: (-gap.priority_score, gap.skill.lower()))

        required_weight = len(required) * 2
        preferred_weight = len(preferred)
        matched_weight = len(matched_required) * 2 + len(matched_preferred)
        coverage_score = clamp_score((matched_weight / max(required_weight + preferred_weight, 1)) * 100)
        return SkillGapResult(
            missing_skills=tuple(gaps),
            matched_required_skills=matched_required,
            matched_preferred_skills=matched_preferred,
            coverage_score=coverage_score,
        )

    def _build_gap(self, skill: str, required: bool, job_search: str) -> SkillGap:
        skill_lower = lower_normalized(skill)
        evidence_count = len(_skill_pattern(skill_lower).findall(job_search)) if job_search else 0
        category = skill_category(skill)
        category_boost = 8 if category in {"programming_languages", "backend", "frontend", "databases", "cloud_devops"} else 4
        score = (72 if required else 42) + min(evidence_count, 5) * 5 + category_boost
        priority_score = clamp_score(score)
        if priority_score >= 85:
            priority = "critical"
        elif priority_score >= 70:
            priority = "high"
        elif priority_score >= 50:
            priority = "medium"
        else:
            priority = "low"
        reason = "Required by the job and not found in the resume." if required else "Preferred by the job and not found in the resume."
        if evidence_count:
            reason = f"{reason} Mentioned {evidence_count} time(s) in the job text."
        return SkillGap(skill, category, priority, priority_score, required, evidence_count, reason)


class JobMatchAlgorithm:
    def match(
        self,
        resume_text: str | None,
        job_description: str | None,
        user_skills: Iterable[str] | None = None,
        required_skills: Iterable[str] | None = None,
        preferred_skills: Iterable[str] | None = None,
    ) -> JobMatchResult:
        resume = normalize_text(resume_text)
        job = normalize_text(job_description)
        extracted_resume_skills = skill_extraction_engine.extract(resume)
        extracted_job_skills = skill_extraction_engine.extract(job)

        candidate_skills = unique_preserving_order(
            normalize_skill_name(skill) for skill in (user_skills or extracted_resume_skills.skills)
        )
        required = unique_preserving_order(
            normalize_skill_name(skill) for skill in (required_skills or extracted_job_skills.skills[:12])
        )
        preferred = unique_preserving_order(normalize_skill_name(skill) for skill in (preferred_skills or ()))
        if not preferred and extracted_job_skills.skills:
            required_set = {lower_normalized(skill) for skill in required}
            preferred = tuple(skill for skill in extracted_job_skills.skills if lower_normalized(skill) not in required_set)[:10]

        gap_result = skill_gap_analysis_engine.analyze(candidate_skills, required, preferred, job)
        skill_score = self._skill_similarity(candidate_skills, required, preferred)
        keyword_result = keyword_matching_engine.match(resume, job, required_keywords=required, optional_keywords=preferred)
        experience_score = self._experience_fit(resume, job)
        education_score = self._education_fit(resume, job)
        score = clamp_score(
            skill_score * 0.45
            + keyword_result.score * 0.25
            + experience_score * 0.20
            + education_score * 0.10
        )

        matched = unique_preserving_order((*gap_result.matched_required_skills, *gap_result.matched_preferred_skills))
        explanation = self._explain(score, skill_score, keyword_result.score, experience_score, education_score, gap_result)
        return JobMatchResult(
            score=score,
            skill_score=skill_score,
            keyword_score=keyword_result.score,
            experience_score=experience_score,
            education_score=education_score,
            matched_skills=matched,
            missing_required_skills=tuple(gap.skill for gap in gap_result.missing_skills if gap.required),
            missing_preferred_skills=tuple(gap.skill for gap in gap_result.missing_skills if not gap.required),
            explanation=explanation,
            details={
                "keyword_match": keyword_result.to_dict(),
                "skill_gap": gap_result.to_dict(),
                "candidate_skill_count": len(candidate_skills),
                "required_skill_count": len(required),
                "preferred_skill_count": len(preferred),
            },
        )

    def _skill_similarity(self, candidate_skills: Sequence[str], required: Sequence[str], preferred: Sequence[str]) -> float:
        candidate = {lower_normalized(skill) for skill in candidate_skills}
        skill_weights: dict[str, float] = {}
        for skill in required:
            skill_weights[lower_normalized(skill)] = 2.0
        for skill in preferred:
            skill_weights.setdefault(lower_normalized(skill), 1.0)

        if not skill_weights:
            return 0.0

        candidate_vector = {skill: 1.0 for skill in candidate}
        job_vector = skill_weights
        cosine = cosine_similarity(candidate_vector, job_vector)
        required_coverage = sum(1 for skill in required if lower_normalized(skill) in candidate) / max(len(required), 1)
        preferred_coverage = sum(1 for skill in preferred if lower_normalized(skill) in candidate) / max(len(preferred), 1) if preferred else 1
        return clamp_score((cosine * 0.35 + required_coverage * 0.50 + preferred_coverage * 0.15) * 100)

    def _experience_fit(self, resume_text: str, job_text: str) -> float:
        required_years = _required_years(job_text)
        candidate_years = _candidate_years(resume_text)
        experience_section = extract_sections(resume_text).get("experience", "")

        if required_years == 0:
            base = 70 if experience_section or DATE_RANGE_RE.search(resume_text) else 45
        elif candidate_years >= required_years:
            base = 90
        else:
            base = 45 + (candidate_years / max(required_years, 1)) * 40

        impact_bonus = min(len(QUANTIFIED_IMPACT_RE.findall(resume_text)), 5) * 2
        action_bonus = min(sum(1 for token in tokenize(experience_section) if token in ACTION_VERBS), 8)
        return clamp_score(base + impact_bonus + action_bonus)

    def _education_fit(self, resume_text: str, job_text: str) -> float:
        job_requires_degree = bool(DEGREE_RE.search(job_text))
        resume_has_degree = bool(DEGREE_RE.search(resume_text))
        resume_has_cert = bool(CERTIFICATION_RE.search(resume_text))
        if not job_requires_degree:
            return clamp_score(70 + (15 if resume_has_degree else 0) + (10 if resume_has_cert else 0))
        if resume_has_degree:
            return clamp_score(90 + (5 if resume_has_cert else 0))
        return 35.0

    def _explain(
        self,
        score: float,
        skill_score: float,
        keyword_score: float,
        experience_score: float,
        education_score: float,
        gap_result: SkillGapResult,
    ) -> tuple[str, ...]:
        messages = [
            f"Overall job match is {score:.1f}/100.",
            f"Skill alignment contributed {skill_score:.1f}/100.",
            f"Keyword coverage contributed {keyword_score:.1f}/100.",
            f"Experience fit contributed {experience_score:.1f}/100.",
            f"Education fit contributed {education_score:.1f}/100.",
        ]
        critical = [gap.skill for gap in gap_result.missing_skills if gap.priority == "critical"]
        if critical:
            messages.append("Critical missing skills: " + ", ".join(critical[:5]) + ".")
        return tuple(messages)


class ResumeCompletenessScorer:
    SECTION_WEIGHTS = {
        "contact": 15.0,
        "summary": 10.0,
        "skills": 15.0,
        "experience": 25.0,
        "education": 15.0,
        "projects": 10.0,
        "certifications": 5.0,
        "achievements": 5.0,
    }

    def score(self, resume: str | Mapping[str, Any] | None) -> CompletenessResult:
        return self.analyze_completeness(resume)

    def analyze_completeness(self, resume: str | Mapping[str, Any] | None) -> CompletenessResult:
        sections = _coerce_sections(resume)
        section_results: list[SectionCompleteness] = []
        suggestions: list[str] = []

        for section, weight in self.SECTION_WEIGHTS.items():
            content = normalize_text(sections.get(section, ""))
            section_score, section_suggestions = self._score_section(section, content, sections)
            present = bool(content)
            section_results.append(SectionCompleteness(section, section_score, weight, present, tuple(section_suggestions)))
            suggestions.extend(section_suggestions)

        total = sum(result.score * (result.weight / 100) for result in section_results)
        missing = tuple(result.section for result in section_results if not result.present)
        return CompletenessResult(
            score=clamp_score(total),
            sections=tuple(section_results),
            missing_sections=missing,
            suggestions=tuple(dict.fromkeys(suggestions))[:12],
        )

    def _score_section(self, section: str, content: str, sections: Mapping[str, str]) -> tuple[float, list[str]]:
        if section == "contact":
            return self._score_contact(content or "\n".join(sections.values()))
        if not content:
            return 0.0, [f"Add a {section.replace('_', ' ')} section."]
        if section == "summary":
            words = tokenize(content, keep_stop_words=True)
            score = 100 if 35 <= len(words) <= 90 else max(40, min(len(words) * 2.5, 85))
            suggestion = [] if score >= 80 else ["Write a 3-5 line professional summary tailored to the target role."]
            return clamp_score(score), suggestion
        if section == "skills":
            extracted = skill_extraction_engine.extract(content)
            category_count = len(extracted.skills_by_category)
            score = min(len(extracted.skills) * 7 + category_count * 8, 100)
            suggestion = [] if score >= 80 else ["Add a focused technical skills section with grouped tools and languages."]
            return clamp_score(score), suggestion
        if section == "experience":
            bullets = len(BULLET_RE.findall(content))
            dates = len(DATE_RANGE_RE.findall(content)) or len(YEAR_RE.findall(content))
            action_count = sum(1 for token in tokenize(content) if token in ACTION_VERBS)
            impact_count = len(QUANTIFIED_IMPACT_RE.findall(content))
            score = bullets * 8 + min(dates, 4) * 10 + min(action_count, 10) * 3 + min(impact_count, 8) * 5
            suggestion = [] if score >= 80 else ["Use action verbs, dates, and quantified impact in work experience bullets."]
            return clamp_score(score), suggestion
        if section == "education":
            score = 80 if DEGREE_RE.search(content) else 45
            if YEAR_RE.search(content):
                score += 10
            if re.search(r"\b(?:university|college|institute|school)\b", content, re.IGNORECASE):
                score += 10
            suggestion = [] if score >= 80 else ["Add degree, institution, field of study, and graduation year."]
            return clamp_score(score), suggestion
        if section == "projects":
            bullets = len(BULLET_RE.findall(content))
            skills = len(skill_extraction_engine.extract(content).skills)
            score = min(40 + bullets * 10 + skills * 5, 100)
            suggestion = [] if score >= 80 else ["Add project outcomes, tech stack, links, and measurable results."]
            return clamp_score(score), suggestion
        if section == "certifications":
            score = 100 if CERTIFICATION_RE.search(content) else min(len(tokenize(content)) * 5, 70)
            suggestion = [] if score >= 80 else ["List relevant certifications with issuer and completion date."]
            return clamp_score(score), suggestion
        if section == "achievements":
            impact_count = len(QUANTIFIED_IMPACT_RE.findall(content))
            score = min(45 + impact_count * 15 + len(BULLET_RE.findall(content)) * 8, 100)
            suggestion = [] if score >= 80 else ["Add awards, publications, leadership, or measurable achievements."]
            return clamp_score(score), suggestion
        return 0.0, []

    def _score_contact(self, content: str) -> tuple[float, list[str]]:
        score = 0.0
        suggestions: list[str] = []
        if EMAIL_RE.search(content):
            score += 30
        else:
            suggestions.append("Add a professional email address.")
        if PHONE_RE.search(content):
            score += 25
        else:
            suggestions.append("Add a phone number.")
        if LINKEDIN_RE.search(content):
            score += 20
        else:
            suggestions.append("Add a LinkedIn profile link.")
        if GITHUB_RE.search(content) or URL_RE.search(content):
            score += 15
        if re.search(r"\b(?:india|delhi|mumbai|bengaluru|bangalore|hyderabad|pune|chennai|kolkata|remote)\b", content, re.IGNORECASE):
            score += 10
        return clamp_score(score), suggestions


class ATSScoringAlgorithm:
    WEIGHTS = {
        "keywords": 0.30,
        "formatting": 0.20,
        "experience": 0.25,
        "skills": 0.15,
        "education": 0.10,
    }

    def score(self, resume_text: str | Mapping[str, Any] | None) -> dict[str, Any]:
        """Legacy score method for backward compatibility."""
        if isinstance(resume_text, Mapping):
            result = self.analyze(None, parsed_sections=resume_text)
        else:
            result = self.analyze(resume_text)
        return {
            "total_score": result.score,
            "breakdown": result.breakdown,
            "suggestions": result.suggestions,
            "matched_keywords": result.matched_keywords,
            "missing_keywords": result.missing_keywords,
        }

    def analyze(
        self,
        resume_text: str | None,
        job_description: str | None = None,
        target_keywords: Iterable[str] | None = None,
        parsed_sections: Mapping[str, Any] | None = None,
    ) -> ATSScoreResult:
        # FIX: Build resume text from parsed_sections if plain_text is empty/missing
        resume = normalize_text(resume_text)
        if not resume and parsed_sections:
            resume = normalize_text(_build_text_from_sections(parsed_sections))
        
        if not resume:
            return ATSScoreResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {}, ("Add resume content before running ATS analysis.",), (), ())

        sections = _coerce_sections(parsed_sections or resume)
        target_keyword_tuple = tuple(target_keywords or ())
        keyword_result = keyword_matching_engine.match(
            resume,
            job_description or " ".join(target_keyword_tuple),
            required_keywords=target_keyword_tuple,
        )
        keyword_score = keyword_result.score if (job_description or target_keyword_tuple) else self._generic_keyword_score(resume)
        formatting_score = self._formatting_score(resume, sections)
        experience_score = self._experience_score(resume, sections)
        skills_score = self._skills_score(resume, sections)
        education_score = self._education_score(resume, sections)

        breakdown = {
            "keywords": clamp_score(keyword_score),
            "formatting": formatting_score,
            "experience": experience_score,
            "skills": skills_score,
            "education": education_score,
        }
        total = sum(breakdown[name] * weight for name, weight in self.WEIGHTS.items())
        suggestions = self._suggestions(breakdown, keyword_result)
        return ATSScoreResult(
            score=clamp_score(total),
            keyword_score=breakdown["keywords"],
            formatting_score=breakdown["formatting"],
            experience_score=breakdown["experience"],
            skills_score=breakdown["skills"],
            education_score=breakdown["education"],
            breakdown=breakdown,
            suggestions=suggestions,
            matched_keywords=keyword_result.matched_keywords,
            missing_keywords=keyword_result.missing_keywords,
        )

    def _generic_keyword_score(self, resume: str) -> float:
        extracted = skill_extraction_engine.extract(resume)
        action_count = sum(1 for token in tokenize(resume) if token in ACTION_VERBS)
        score = len(extracted.skills) * 4 + len(extracted.skills_by_category) * 8 + min(action_count, 12) * 2
        return clamp_score(score)

    def _formatting_score(self, resume: str, sections: Mapping[str, str]) -> float:
        score = 0.0
        line_count = len([line for line in resume.splitlines() if line.strip()])
        word_count = len(tokenize(resume, keep_stop_words=True))
        
        # FIX: Lower word count thresholds for fresher / short resumes
        if 350 <= word_count <= 900:
            score += 25
        elif 250 <= word_count < 350 or 900 < word_count <= 1100:
            score += 15
        elif 150 <= word_count < 250:
            score += 10
        elif 80 <= word_count < 150:
            score += 5
        
        if line_count >= 8:
            score += 15
        if len(sections) >= 5:
            score += 25
        elif len(sections) >= 3:
            score += 15
        if BULLET_RE.search(resume):
            score += 15
        if not _has_excessive_symbols(resume):
            score += 10
        if max((len(line) for line in resume.splitlines()), default=0) <= 140:
            score += 10
        return clamp_score(score)

    def _experience_score(self, resume: str, sections: Mapping[str, str]) -> float:
        content = sections.get("experience", resume)
        if not content:
            return 0.0
        
        # FIX: Give base score for having experience section at all
        base_score = 15.0
        
        bullets = len(BULLET_RE.findall(content))
        date_ranges = len(DATE_RANGE_RE.findall(content))
        years = _candidate_years(content)
        action_count = sum(1 for token in tokenize(content) if token in ACTION_VERBS)
        quantified = len(QUANTIFIED_IMPACT_RE.findall(content))
        score = base_score + bullets * 7 + date_ranges * 12 + min(years, 8) * 5 + min(action_count, 12) * 3 + min(quantified, 8) * 5
        return clamp_score(score)

    def _skills_score(self, resume: str, sections: Mapping[str, str]) -> float:
        skills_text = sections.get("skills", resume)
        if not skills_text:
            return 0.0
        
        # FIX: Give base score for having skills section
        base_score = 10.0
        
        extracted = skill_extraction_engine.extract(skills_text)
        score = base_score + len(extracted.skills) * 5 + len(extracted.skills_by_category) * 10 + extracted.confidence_score * 0.25
        return clamp_score(score)

    def _education_score(self, resume: str, sections: Mapping[str, str]) -> float:
        content = sections.get("education", resume)
        if not content:
            return 0.0
        
        # FIX: Give base score for having education section
        base_score = 10.0
        
        score = base_score
        if DEGREE_RE.search(content):
            score += 55
        if re.search(r"\b(?:university|college|institute|school)\b", content, re.IGNORECASE):
            score += 20
        if YEAR_RE.search(content):
            score += 15
        if CERTIFICATION_RE.search(resume):
            score += 10
        return clamp_score(score)

    def _suggestions(self, breakdown: Mapping[str, float], keyword_result: KeywordMatchResult) -> tuple[str, ...]:
        suggestions: list[str] = []
        if breakdown["keywords"] < 75:
            suggestions.extend(keyword_result.suggestions[:5] or ("Add more role-specific keywords from the target job.",))
        if breakdown["formatting"] < 75:
            suggestions.append("Use standard resume sections, concise lines, and bullet points for ATS parsing.")
        if breakdown["experience"] < 75:
            suggestions.append("Strengthen experience bullets with action verbs, dates, and measurable impact.")
        if breakdown["skills"] < 75:
            suggestions.append("Add a grouped skills section with the most relevant technical tools.")
        if breakdown["education"] < 70:
            suggestions.append("Include education details such as degree, institution, and graduation year.")
        return tuple(dict.fromkeys(suggestions))[:10]


def _snippet(text: str, start: int, end: int, radius: int = 42) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def _skill_pattern(skill: str) -> re.Pattern[str]:
    escaped = re.escape(skill)
    return re.compile(rf"(?<![a-z0-9+#]){escaped}(?![a-z0-9+#])", re.IGNORECASE)


def _phrase_present(keyword: str, resume_search: str) -> bool:
    keyword_lower = lower_normalized(keyword)
    if not keyword_lower:
        return False
    if _skill_pattern(keyword_lower).search(resume_search):
        return True
    terms = tokenize(keyword_lower)
    if len(terms) <= 1:
        return False
    return all(_skill_pattern(term).search(resume_search) for term in terms)


def _inverse_document_frequency(documents: Sequence[Sequence[str]]) -> dict[str, float]:
    document_count = len(documents)
    document_frequency: Counter[str] = Counter()
    for document in documents:
        document_frequency.update(set(document))
    return {
        term: math.log((document_count + 1) / (frequency + 1)) + 1
        for term, frequency in document_frequency.items()
    }


def _tfidf_vector(tokens: Sequence[str], idf: Mapping[str, float]) -> dict[str, float]:
    tf = term_frequency(tokens)
    return {term: frequency * idf.get(term, 1.0) for term, frequency in tf.items()}


def _top_tokens(text: str, limit: int) -> tuple[str, ...]:
    counts = Counter(tokenize(text))
    return tuple(token for token, _ in counts.most_common(limit))


def _important_phrases(text: str) -> tuple[str, ...]:
    tokens = tokenize(text)
    phrases: Counter[str] = Counter()
    for size in (2, 3):
        for index in range(0, max(len(tokens) - size + 1, 0)):
            phrase_tokens = tokens[index : index + size]
            if any(token in STOP_WORDS for token in phrase_tokens):
                continue
            phrase = " ".join(phrase_tokens)
            if len(phrase) >= 8:
                phrases[phrase] += 1
    return tuple(phrase for phrase, _ in phrases.most_common(15))


def _coerce_sections(resume: str | Mapping[str, Any] | None) -> dict[str, str]:
    if resume is None:
        return {}
    if isinstance(resume, str):
        return extract_sections(resume)

    sections: dict[str, str] = {}
    for key, value in resume.items():
        canonical = canonical_section_name(str(key).replace("_", " "))
        if isinstance(value, str):
            sections[canonical] = normalize_text(value)
        elif isinstance(value, Mapping):
            text_parts = [str(item) for item in value.values() if item is not None]
            sections[canonical] = normalize_text("\n".join(text_parts))
        elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            sections[canonical] = normalize_text("\n".join(str(item) for item in value))
        else:
            sections[canonical] = normalize_text(str(value))
    return sections


# FIX: New helper to build plain text from parsed sections when plain_text is empty
def _build_text_from_sections(parsed_sections: Mapping[str, Any] | None) -> str:
    if not parsed_sections:
        return ""
    parts: list[str] = []
    for key, value in parsed_sections.items():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, Mapping):
            parts.extend(str(v) for v in value.values() if v is not None)
        elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            parts.extend(str(v) for v in value)
        else:
            parts.append(str(value))
    return "\n\n".join(parts)


def _required_years(job_text: str) -> float:
    patterns = (
        r"\b(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience\b",
        r"\bminimum\s+(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\b",
        r"\b(\d+(?:\.\d+)?)\s*-\s*\d+(?:\.\d+)?\s*(?:years?|yrs?)\b",
    )
    values: list[float] = []
    for pattern in patterns:
        values.extend(float(match) for match in re.findall(pattern, job_text, re.IGNORECASE))
    return min(values) if values else 0.0


def _candidate_years(resume_text: str) -> float:
    explicit = re.findall(r"\b(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience\b", resume_text, re.IGNORECASE)
    if explicit:
        return max(float(value) for value in explicit)

    years = sorted(int(year) for year in YEAR_RE.findall(resume_text))
    if len(years) >= 2:
        current_year = 2026
        first = min(years)
        last = max(max(years), current_year if re.search(r"\b(?:present|current)\b", resume_text, re.IGNORECASE) else max(years))
        return max(0.0, min(float(last - first), 40.0))
    return 0.0


def _has_excessive_symbols(text: str) -> bool:
    if not text:
        return False
    symbol_count = sum(1 for char in text if not char.isalnum() and not char.isspace() and char not in ".:,;()/+-#@%&")
    return symbol_count / max(len(text), 1) > 0.03


skill_extraction_engine = SkillExtractionEngine()
keyword_matching_engine = KeywordMatchingEngine()
skill_gap_analysis_engine = SkillGapAnalysisAlgorithm()
job_match_engine = JobMatchAlgorithm()
resume_completeness_scorer = ResumeCompletenessScorer()
ats_scoring_engine = ATSScoringAlgorithm()


__all__ = [
    "ATSScoreResult",
    "ATSScoringEngine",
    "CompletenessResult",
    "ExtractedSkill",
    "JobMatchEngine",
    "JobMatchResult",
    "KeywordMatchResult",
    "KeywordMatchingEngine",
    "ResumeCompletenessScorer",
    "SectionCompleteness",
    "SkillExtractionEngine",
    "SkillExtractionResult",
    "SkillGap",
    "SkillGapAnalysisEngine",
    "SkillGapResult",
    "ats_scoring_engine",
    "canonical_section_name",
    "cosine_similarity",
    "extract_sections",
    "job_match_engine",
    "keyword_matching_engine",
    "normalize_skill_name",
    "normalize_text",
    "resume_completeness_scorer",
    "skill_extraction_engine",
    "skill_gap_analysis_engine",
    "tokenize",
]

ATSScoringEngine = ATSScoringAlgorithm
JobMatchEngine = JobMatchAlgorithm
SkillGapAnalysisEngine = SkillGapAnalysisAlgorithm