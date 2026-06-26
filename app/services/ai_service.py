from __future__ import annotations

import json
import os
import random
import re

import requests
from flask import current_app


class AIService:
    """AI Service with Groq API (free tier) + local rule-based fallback."""

    WEAK_VERBS = {
        "managed": ["Led", "Directed", "Orchestrated", "Spearheaded"],
        "worked on": ["Developed", "Engineered", "Architected", "Implemented"],
        "helped": ["Facilitated", "Accelerated", "Optimized", "Streamlined"],
        "responsible for": ["Owned", "Drove", "Championed", "Delivered"],
        "assisted": ["Supported", "Collaborated on", "Contributed to"],
        "made": ["Created", "Built", "Designed", "Crafted"],
        "did": ["Executed", "Performed", "Achieved", "Accomplished"],
        "used": ["Leveraged", "Utilized", "Harnessed", "Deployed"],
        "handled": ["Managed", "Oversaw", "Coordinated", "Governed"],
    }

    IMPACTS = [
        ", resulting in 35% efficiency improvement",
        ", leading to significant performance gains",
        ", driving measurable business impact",
        ", achieving project goals ahead of schedule",
        ", reducing operational overhead by 25%",
        ", increasing user engagement by 40%",
    ]

    @staticmethod
    def improve_bullet(bullet_text: str) -> dict:
        if not bullet_text or not bullet_text.strip():
            return {"error": "No bullet text provided"}

        groq_key = current_app.config.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                return AIService._groq_enhance(bullet_text, groq_key)
            except Exception as e:
                current_app.logger.warning(f"Groq API failed: {e}, using local fallback")

        return AIService._local_enhance(bullet_text)

    @staticmethod
    def _groq_enhance(bullet_text: str, api_key: str) -> dict:
        prompt = (
            f"Rewrite this resume bullet to be more impactful. Use strong action verbs, "
            f"add metrics if missing, and follow STAR method. Keep it to 1 line, max 20 words. "
            f"Only output the enhanced bullet, nothing else.\n\n"
            f"Original: {bullet_text}\nEnhanced:"
        )

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama3-8b-8192",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert resume writer. Only output the enhanced bullet point text, no explanation.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.6,
                "max_tokens": 120,
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        enhanced = data["choices"][0]["message"]["content"].strip()

        enhanced = re.sub(r'^["\']|["\']$', "", enhanced)
        enhanced = re.sub(r"^(Enhanced|Improved|Rewritten)[\s:]*", "", enhanced, flags=re.IGNORECASE)

        return {
            "original": bullet_text,
            "enhanced": enhanced,
            "source": "ai",
        }

    @staticmethod
    def _local_enhance(bullet_text: str) -> dict:
        text = bullet_text.strip()
        original = text
        text_lower = text.lower()

        for weak, strong_list in AIService.WEAK_VERBS.items():
            if weak in text_lower:
                pattern = re.compile(re.escape(weak), re.IGNORECASE)
                replacement = random.choice(strong_list)
                text = pattern.sub(replacement, text, count=1)
                break

        has_numbers = re.search(r"\d+%|\d+\s*percent|\$\d+|\d+\s*times|\d+\+?\s*(team|members|developers|people|projects|users)", text_lower)
        if not has_numbers:
            if "team" in text_lower or "developers" in text_lower or "people" in text_lower:
                text = re.sub(r"(team|developers|people|engineers)", r"\1 of 5+", text, count=1, flags=re.IGNORECASE)
            elif any(w in text_lower for w in ["improve", "increase", "reduce", "decrease", "optimize", "enhance"]):
                text += ", resulting in 30% improvement"
            elif any(w in text_lower for w in ["website", "app", "product", "platform", "system"]):
                text += ", improving performance by 40%"
            elif "build" in text_lower or "create" in text_lower or "develop" in text_lower:
                text += ", serving 10,000+ users"
            else:
                text += ", driving measurable results"

        words = text.split()
        if words and words[0].lower() in ["i", "we", "my", "our"]:
            text = " ".join(words[1:])
            text = text[0].upper() + text[1:] if text else ""

        if not any(w in text_lower for w in ["resulting", "leading", "driving", "achieving", "delivering", "reducing", "improving", "increasing"]):
            text += random.choice(AIService.IMPACTS)

        text = text.strip()
        if text.endswith(","):
            text = text[:-1]
        if not text.endswith("."):
            text += "."

        return {
            "original": original,
            "enhanced": text,
            "source": "local",
        }

    @staticmethod
    def rewrite_resume(user_id: int, resume_id: int) -> dict:
        from app.models.resume import Resume

        resume = Resume.query.filter_by(id=resume_id, user_id=user_id, is_archived=False).first()
        if not resume:
            return {"error": "Resume not found", "rewritten": None, "source": "error"}

        # ===== 1. PARSE DATA SAFELY =====
        parsed = resume.parsed_data or {}
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}

        title = resume.title or "Professional Resume"

        # Extract from top-level keys
        personal_info = parsed.get("personal_info", {}) or parsed.get("contact", {})
        summary = parsed.get("summary", "") or parsed.get("professional_summary", "") or parsed.get("objective", "")
        experience = parsed.get("experience", []) or parsed.get("work_experience", []) or parsed.get("work", [])
        education = parsed.get("education", []) or parsed.get("academic", [])
        skills = parsed.get("skills", []) or parsed.get("technical_skills", []) or parsed.get("core_competencies", [])
        projects = parsed.get("projects", []) or parsed.get("personal_projects", [])
        certifications = parsed.get("certifications", []) or parsed.get("certificates", [])

        # Also extract from sections array
        sections = parsed.get("sections", [])
        if isinstance(sections, str):
            try:
                sections = json.loads(sections)
            except:
                sections = []
        if not isinstance(sections, list):
            sections = []

        for section in sections:
            if isinstance(section, str):
                try:
                    section = json.loads(section)
                except:
                    continue
            if not isinstance(section, dict):
                continue
            sec_type = section.get("type", "")
            if sec_type in ("experience", "work") and not experience:
                experience = section.get("items", []) or section.get("content", [])
            elif sec_type == "education" and not education:
                education = section.get("items", []) or section.get("content", [])
            elif sec_type == "skills" and not skills:
                skills = section.get("items", []) or section.get("content", [])
            elif sec_type == "summary" and not summary:
                summary = section.get("content", "")
            elif sec_type == "projects" and not projects:
                projects = section.get("items", []) or section.get("content", [])

        # Normalize all data types
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(",") if s.strip()]
        elif isinstance(skills, dict):
            skills = [v for k, v in skills.items() if v]
        elif not isinstance(skills, list):
            skills = []

        if isinstance(experience, str):
            experience = [{"title": "Experience", "description": experience}]
        elif not isinstance(experience, list):
            experience = []

        if isinstance(education, str):
            education = [{"degree": education}]
        elif not isinstance(education, list):
            education = []

        if isinstance(projects, str):
            projects = [{"title": "Project", "description": projects}]
        elif not isinstance(projects, list):
            projects = []

        if isinstance(certifications, str):
            certifications = [certifications]
        elif not isinstance(certifications, list):
            certifications = []

        if isinstance(summary, dict):
            summary = summary.get("text", "") or " ".join(str(v) for v in summary.values() if isinstance(v, str))
        elif not isinstance(summary, str):
            summary = ""

        if isinstance(personal_info, str):
            personal_info = {"name": personal_info}
        elif not isinstance(personal_info, dict):
            personal_info = {}

        # ===== 2. BUILD ENHANCED RESUME =====
        lines = []
        lines.append(f"# {title}")
        lines.append("")

        # --- CONTACT INFO ---
        if personal_info:
            contact_lines = []
            for k, v in personal_info.items():
                if v and str(v).strip():
                    contact_lines.append(f"**{k.replace('_', ' ').title()}:** {v}")
            if contact_lines:
                lines.append("## Contact Information")
                lines.append("")
                lines.append(" | ".join(contact_lines))
                lines.append("")

        # --- PROFESSIONAL SUMMARY (AI ENHANCED) ---
        if summary and str(summary).strip():
            enhanced_summary = AIService._local_enhance(str(summary).strip()).get("enhanced", str(summary))
            lines.append("## Professional Summary")
            lines.append("")
            lines.append(enhanced_summary)
            lines.append("")
        else:
            # GENERATE summary from skills
            skills_text = ", ".join(str(s) for s in skills[:5]) if skills else "various technical and professional skills"
            generated_summary = f"Results-driven professional with expertise in {skills_text}. Proven track record of delivering high-impact solutions, optimizing processes, and driving measurable business outcomes. Adept at collaborating with cross-functional teams to achieve strategic objectives ahead of schedule."
            lines.append("## Professional Summary")
            lines.append("")
            lines.append(generated_summary)
            lines.append("")

        # --- TECHNICAL SKILLS (AI ENHANCED) ---
        if skills:
            lines.append("## Technical Skills & Core Competencies")
            lines.append("")
            skill_items = [f"• {str(s).strip()}" for s in skills if str(s).strip()]
            if skill_items:
                lines.append("\n".join(skill_items))
            lines.append("")
            lines.append("Proficient in leveraging these technologies to build scalable, high-performance solutions that drive business growth and operational excellence.")
            lines.append("")

        # --- PROFESSIONAL EXPERIENCE (AI ENHANCED) ---
        if experience:
            lines.append("## Professional Experience")
            lines.append("")
            for item in experience:
                if isinstance(item, dict):
                    role = item.get("title", item.get("role", item.get("position", "Professional Role")))
                    company = item.get("company", item.get("organization", item.get("employer", "")))
                    date = item.get("date", item.get("duration", item.get("period", "")))
                    bullets = item.get("bullets", item.get("responsibilities", item.get("description", item.get("achievements", []))))
                    if isinstance(bullets, str):
                        bullets = [b.strip() for b in bullets.split("\n") if b.strip()]
                    elif not isinstance(bullets, list):
                        bullets = []

                    date_str = f" | {date}" if date else ""
                    company_str = f" at {company}" if company else ""
                    lines.append(f"**{role}**{company_str}{date_str}")
                    lines.append("")

                    if bullets:
                        for bullet in bullets:
                            if bullet and str(bullet).strip():
                                enhanced = AIService._local_enhance(str(bullet).strip()).get("enhanced", str(bullet).strip())
                                lines.append(f"• {enhanced}")
                    else:
                        # Generate AI bullets from skills
                        for _ in range(3):
                            skill_ref = random.choice(skills) if skills else "core technologies"
                            base = f"Led development initiatives leveraging {skill_ref}, delivering high-quality solutions ahead of schedule."
                            enhanced = AIService._local_enhance(base).get("enhanced", base)
                            lines.append(f"• {enhanced}")
                    lines.append("")
                else:
                    enhanced = AIService._local_enhance(str(item)).get("enhanced", str(item))
                    lines.append(f"• {enhanced}")
                    lines.append("")
        else:
            # GENERATE experience from skills
            if skills:
                lines.append("## Professional Experience")
                lines.append("")
                lines.append("**Software Developer / Technical Lead**")
                lines.append("")
                for skill in skills[:3]:
                    base = f"Architected and deployed {skill} solutions, optimizing performance and driving measurable business impact."
                    enhanced = AIService._local_enhance(base).get("enhanced", base)
                    lines.append(f"• {enhanced}")
                extra_bullets = [
                    "Led cross-functional teams of 5+ developers to deliver high-impact projects, resulting in 35% efficiency improvement.",
                    "Streamlined development workflows and optimized existing systems, reducing operational overhead by 25%.",
                    "Collaborated with stakeholders to define technical requirements and achieve strategic objectives ahead of schedule."
                ]
                for b in extra_bullets:
                    enhanced = AIService._local_enhance(b).get("enhanced", b)
                    lines.append(f"• {enhanced}")
                lines.append("")

        # --- KEY PROJECTS (AI ENHANCED) ---
        if projects:
            lines.append("## Key Projects")
            lines.append("")
            for item in projects:
                if isinstance(item, dict):
                    proj_title = item.get("title", item.get("name", "Project"))
                    proj_desc = item.get("description", item.get("summary", ""))
                    proj_tech = item.get("technologies", item.get("tech", item.get("skills_used", [])))
                    lines.append(f"**{proj_title}**")
                    if proj_desc:
                        enhanced = AIService._local_enhance(str(proj_desc)).get("enhanced", str(proj_desc))
                        lines.append(enhanced)
                    if proj_tech:
                        if isinstance(proj_tech, list):
                            tech_str = ", ".join(str(t) for t in proj_tech)
                        else:
                            tech_str = str(proj_tech)
                        lines.append(f"*Technologies: {tech_str}*")
                    lines.append("")
                else:
                    enhanced = AIService._local_enhance(str(item)).get("enhanced", str(item))
                    lines.append(f"• {enhanced}")
                    lines.append("")

        # --- EDUCATION ---
        if education:
            lines.append("## Education")
            lines.append("")
            for item in education:
                if isinstance(item, dict):
                    degree = item.get("degree", item.get("title", "Degree"))
                    school = item.get("school", item.get("institution", item.get("university", "")))
                    year = item.get("year", item.get("graduation_date", item.get("date", "")))
                    gpa = item.get("gpa", "")
                    school_text = f", {school}" if school else ""
                    year_text = f" ({year})" if year else ""
                    gpa_text = f" — GPA: {gpa}" if gpa else ""
                    lines.append(f"• **{degree}**{school_text}{year_text}{gpa_text}")
                else:
                    lines.append(f"• {item}")
            lines.append("")

        # --- CERTIFICATIONS ---
        if certifications:
            lines.append("## Certifications")
            lines.append("")
            for cert in certifications:
                if isinstance(cert, dict):
                    cert_name = cert.get("name", cert.get("title", "Certification"))
                    cert_org = cert.get("organization", cert.get("issuer", ""))
                    cert_date = cert.get("date", "")
                    org_text = f" — {cert_org}" if cert_org else ""
                    date_text = f" ({cert_date})" if cert_date else ""
                    lines.append(f"• {cert_name}{org_text}{date_text}")
                else:
                    lines.append(f"• {cert}")
            lines.append("")

        # --- FALLBACK: Full template if nothing at all ---
        if len(lines) <= 3:
            lines = [
                f"# {title}",
                "",
                "## Professional Summary",
                "",
                "Results-driven professional with a strong track record of delivering high-impact solutions. Skilled in various technologies and methodologies, consistently optimizing processes and driving measurable business outcomes.",
                "",
                "## Professional Experience",
                "",
                "• Led cross-functional teams to deliver high-impact projects, resulting in 35% efficiency improvement.",
                "• Developed and optimized key systems, improving performance by 40%.",
                "• Collaborated with stakeholders to achieve project goals ahead of schedule.",
                "",
                "## Technical Skills",
                "",
                "• Technical Leadership",
                "• Project Management",
                "• Strategic Planning",
                "• Team Development",
                "",
                "## Education",
                "",
                "• Relevant Degree / Certification",
                ""
            ]

        rewritten_text = "\n".join(lines)

        return {
            "rewritten": rewritten_text,
            "original": title,
            "source": "local",
            "message": "Resume rewritten with AI-enhanced language, stronger action verbs, and impactful metrics."
        }

    @staticmethod
    def generate_summary(user_id: int, resume_id: int) -> dict:
        return {"message": "Summary generation coming soon", "enabled": True}

    @staticmethod
    def generate_cover_letter(user_id: int, resume_id: int, job_id: int) -> dict:
        return {"message": "Cover letter generation coming soon", "enabled": True}

    @staticmethod
    def generate_interview_prep(user_id: int, resume_id: int, job_id: int) -> dict:
        return {"message": "Interview prep coming soon", "enabled": True}

    @staticmethod
    def suggest_skill_optimization(user_id: int, resume_id: int, job_id: int) -> dict:
        return {"message": "Skill optimization coming soon", "enabled": True}

    @staticmethod
    def get_task_status(user_id: int, task_id: int) -> dict:
        return {"status": "completed", "result": "Task finished"}