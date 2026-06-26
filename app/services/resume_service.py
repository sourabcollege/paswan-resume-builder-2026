from __future__ import annotations

import difflib
import copy
import os
import re
import shutil
from dataclasses import dataclass, field
from app.utils import resume_utils
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from flask import current_app
from sqlalchemy.exc import IntegrityError
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models.activity import ActivityLog
from app.models.analytics import ResumeScore
from app.models.resume import Resume, ResumeSection, ResumeVersion
from app.models.user import User
from app.repositories.resumes import ResumeRepository
from app.resume.utils import save_validated_upload as process_upload, validate_resume_upload as validate_upload
from app.utils.offline_engines import ats_scoring_engine, resume_completeness_scorer, skill_extraction_engine


@dataclass(frozen=True)
class ResumeServiceResult:
    success: bool
    message: str
    status_code: int = 200
    data: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class ResumeExportResult:
    filename: str
    mimetype: str
    data: bytes


class ResumeService:
    def __init__(self, resumes: ResumeRepository | None = None) -> None:
        self.resumes = resumes or ResumeRepository()

    def list_resumes(self, user_id: int) -> ResumeServiceResult:
        items = [serialize_resume(resume, self.resumes.get_current_version(resume.id, user_id)) for resume in self.resumes.list_for_user(user_id)]
        return ResumeServiceResult(True, "Resumes loaded.", data={"resumes": items})

    def delete_resume(
        self,
        user_id: int,
        public_id: str,
        *,
        request_meta: dict[str, Any] | None = None,
    ) -> ResumeServiceResult:
        """Delete resume with ownership check, file cleanup, and cascade delete."""
        resume = self.resumes.get_by_public_id_for_user(public_id, user_id)
        if resume is None:
            return ResumeServiceResult(False, "Resume not found.", status_code=404)

        if resume.user_id != user_id:
            return ResumeServiceResult(False, "Unauthorized.", status_code=403)

        title = resume.title or "Untitled"

        # File cleanup: uploaded file
        if resume.storage_path:
            try:
                Path(resume.storage_path).unlink(missing_ok=True)
            except OSError:
                pass

        # File cleanup: generated exports matching this resume's slug
        try:
            gen_base = Path(current_app.config.get("GENERATED_RESUME_FOLDER", "generated_resumes"))
            user_gen_dir = gen_base / str(user_id)
            if user_gen_dir.exists():
                for f in user_gen_dir.iterdir():
                    if f.is_file() and resume.slug in f.name:
                        f.unlink(missing_ok=True)
        except Exception:
            pass

        # File cleanup: extra uploads matching this resume's slug
        try:
            upload_base = Path(current_app.config.get("RESUME_UPLOAD_FOLDER", "uploads/resumes"))
            user_upload_dir = upload_base / str(user_id)
            if user_upload_dir.exists():
                for f in user_upload_dir.iterdir():
                    if f.is_file() and resume.slug in f.name:
                        f.unlink(missing_ok=True)
        except Exception:
            pass

        # Log activity before delete (resume object will be gone after cascade delete)
        self._log_activity(
            user_id,
            "resume_deleted",
            "success",
            resume=resume,
            severity="info",
            details={"deleted_resume_title": title, "deleted_resume_public_id": public_id},
            request_meta=request_meta,
        )

        # Cascade DB delete (versions, sections, scores, job_matches, analytics_history)
        self.resumes.delete(resume)

        return ResumeServiceResult(
            True,
            f"Resume '{title}' deleted successfully.",
            data={"id": public_id, "title": title, "deleted": True},
        )

    def upload_resume(
        self,
        user: User,
        uploaded_file: FileStorage | None,
        *,
        title: str | None = None,
        parse_immediately: bool = True,
        request_meta: dict[str, Any] | None = None,
    ) -> ResumeServiceResult:
        limit_error = self._resume_limit_error(user)
        if limit_error:
            return limit_error

        try:
            validated = resume_utils.validate_resume_upload(
                uploaded_file,
                max_bytes=current_app.config["MAX_CONTENT_LENGTH"],
                allowed_extensions=current_app.config["ALLOWED_RESUME_EXTENSIONS"],
            )
        except resume_utils.ResumeValidationError as exc:
            self._log_activity(user.id, "resume_upload_rejected", "failure", severity="warning", details={"reason": str(exc)}, request_meta=request_meta)
            db.session.commit()
            return ResumeServiceResult(False, str(exc), status_code=400, errors={"file": [str(exc)]})

        storage_path = resume_utils.save_validated_upload(
            validated,
            current_app.config["RESUME_UPLOAD_FOLDER"],
            user.id,
        )
        resume_title = (title or Path(validated.secure_filename).stem or "Uploaded Resume").strip()
        resume = Resume(
            user_id=user.id,
            title=resume_title[:180],
            slug=self._unique_slug(user.id, resume_title),
            source_type="upload",
            original_filename=validated.original_filename,
            storage_path=storage_path,
            file_mime_type=validated.mime_type,
            file_size_bytes=validated.size_bytes,
            checksum_sha256=validated.checksum_sha256,
            parsing_status="pending" if parse_immediately else "not_required",
        )
        self.resumes.add(resume)

        try:
            self.resumes.flush()
            if parse_immediately:
                parse_result = self._parse_and_apply(resume, user.id)
                if not parse_result.success:
                    self._log_activity(
                        user.id,
                        "resume_parse_failed",
                        "failure",
                        resume=resume,
                        severity="warning",
                        details=parse_result.errors,
                        request_meta=request_meta,
                    )
                    db.session.commit()
                    return ResumeServiceResult(
                        False,
                        parse_result.message,
                        status_code=422,
                        data={"resume": serialize_resume(resume, self.resumes.get_current_version(resume.id, user.id))},
                        errors=parse_result.errors,
                    )

            self._log_activity(user.id, "resume_uploaded", "success", resume=resume, request_meta=request_meta)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            Path(storage_path).unlink(missing_ok=True)
            return ResumeServiceResult(False, "A resume with this title already exists.", status_code=409)
        except Exception:
            db.session.rollback()
            Path(storage_path).unlink(missing_ok=True)
            raise

        return ResumeServiceResult(
            True,
            "Resume uploaded and parsed." if parse_immediately else "Resume uploaded.",
            status_code=201,
            data={"resume": serialize_resume(resume, self.resumes.get_current_version(resume.id, user.id))},
        )

    def parse_resume(self, user_id: int, public_id: str, *, request_meta: dict[str, Any] | None = None) -> ResumeServiceResult:
        resume = self.resumes.get_by_public_id_for_user(public_id, user_id)
        if resume is None:
            return ResumeServiceResult(False, "Resume not found.", status_code=404)
        result = self._parse_and_apply(resume, user_id)
        self._log_activity(
            user_id,
            "resume_parsed" if result.success else "resume_parse_failed",
            "success" if result.success else "failure",
            resume=resume,
            severity="info" if result.success else "warning",
            details=result.errors,
            request_meta=request_meta,
        )
        db.session.commit()
        return result

    def create_builder_resume(self, user: User, payload: Mapping[str, Any], *, request_meta: dict[str, Any] | None = None) -> ResumeServiceResult:
        limit_error = self._resume_limit_error(user)
        if limit_error:
            return limit_error

        title = str(payload.get("title") or "Untitled Resume").strip()[:180]
        content = _extract_content(payload)
        if not content:
            return ResumeServiceResult(
                False,
                "Resume content must include at least one section.",
                status_code=400,
                errors={"content": ["Add at least one resume section."]},
            )
        plain_text = resume_utils.plain_text_from_content(content)
        skills = skill_extraction_engine.extract(plain_text).skills
        completeness = resume_completeness_scorer.score(content).score
        resume = Resume(
            user_id=user.id,
            title=title,
            slug=self._unique_slug(user.id, title),
            source_type="builder",
            parsing_status="not_required",
            parsed_data={"sections": content},
            extracted_skills=list(skills),
        )
        version = ResumeVersion(
            user_id=user.id,
            resume=resume,
            version_number=1,
            label=str(payload.get("label") or "Initial Draft")[:180],
            status="active",
            template_key=str(payload.get("template_key") or "classic")[:80],
            content=content,
            plain_text=plain_text,
            is_current=True,
            completeness_snapshot=completeness,
        )
        self.resumes.add(resume)
        self.resumes.add(version)
        self.resumes.flush()
        self._replace_sections(version, content, source="manual")
        self._record_score(version, plain_text, content)
        self._log_activity(user.id, "resume_builder_created", "success", resume=resume, request_meta=request_meta)
        db.session.commit()
        return ResumeServiceResult(
            True,
            "Resume created.",
            status_code=201,
            data={"resume": serialize_resume(resume, version), "version": serialize_version(version)},
        )

    def get_builder_payload(self, user_id: int, public_id: str) -> ResumeServiceResult:
        resume = self.resumes.get_by_public_id_for_user(public_id, user_id)
        if resume is None:
            return ResumeServiceResult(False, "Resume not found.", status_code=404)
        version = self.resumes.get_current_version(resume.id, user_id)
        return ResumeServiceResult(
            True,
            "Resume loaded.",
            data={"resume": serialize_resume(resume, version), "version": serialize_version(version) if version else None},
        )

    def save_builder_draft(self, user_id: int, public_id: str, payload: Mapping[str, Any], *, request_meta: dict[str, Any] | None = None) -> ResumeServiceResult:
        resume = self.resumes.get_by_public_id_for_user(public_id, user_id)
        if resume is None:
            return ResumeServiceResult(False, "Resume not found.", status_code=404)

        version = self.resumes.get_current_version(resume.id, user_id)
        if version is None:
            limit_error = self._version_limit_error(user_id, resume.id)
            if limit_error:
                return limit_error
            version = ResumeVersion(
                user_id=user_id,
                resume=resume,
                version_number=self.resumes.next_version_number(resume.id),
                label=str(payload.get("label") or "Draft")[:180],
                status="active",
                template_key=str(payload.get("template_key") or "classic")[:80],
                is_current=True,
            )
            self.resumes.add(version)

        content = _extract_content(payload)
        if not content:
            return ResumeServiceResult(
                False,
                "Resume content must include at least one section.",
                status_code=400,
                errors={"content": ["Add at least one resume section."]},
            )
        plain_text = resume_utils.plain_text_from_content(content)
        resume.title = str(payload.get("title") or resume.title).strip()[:180]
        resume.parsed_data = {"sections": content}
        resume.extracted_skills = list(skill_extraction_engine.extract(plain_text).skills)
        version.content = content
        version.plain_text = plain_text
        version.template_key = str(payload.get("template_key") or version.template_key)[:80]
        version.completeness_snapshot = resume_completeness_scorer.score(content).score
        self._replace_sections(version, content, source="manual")
        self._record_score(version, plain_text, content)
        self._log_activity(user_id, "resume_builder_saved", "success", resume=resume, request_meta=request_meta)
        db.session.commit()
        return ResumeServiceResult(
            True,
            "Resume draft saved.",
            data={"resume": serialize_resume(resume, version), "version": serialize_version(version)},
        )

    def list_versions(self, user_id: int, public_id: str) -> ResumeServiceResult:
        resume = self.resumes.get_by_public_id_for_user(public_id, user_id)
        if resume is None:
            return ResumeServiceResult(False, "Resume not found.", status_code=404)
        versions = [serialize_version(version) for version in self.resumes.list_versions(resume.id, user_id)]
        return ResumeServiceResult(True, "Versions loaded.", data={"resume": serialize_resume(resume), "versions": versions})

    def get_version(self, user_id: int, public_id: str, version_public_id: str) -> ResumeServiceResult:
        resume = self.resumes.get_by_public_id_for_user(public_id, user_id)
        version = self.resumes.get_version_by_public_id_for_user(version_public_id, user_id)
        if resume is None or version is None or version.resume_id != resume.id:
            return ResumeServiceResult(False, "Version not found.", status_code=404)
        sections = self.resumes.list_sections(version.id, user_id)
        return ResumeServiceResult(
            True,
            "Version loaded.",
            data={
                "resume": serialize_resume(resume),
                "version": serialize_version(version),
                "sections": [
                    {
                        "type": section.section_type,
                        "title": section.title,
                        "sort_order": section.sort_order,
                        "content": section.content,
                        "plain_text": section.plain_text,
                    }
                    for section in sections
                ],
            },
        )

    def create_version(self, user_id: int, public_id: str, payload: Mapping[str, Any], *, request_meta: dict[str, Any] | None = None) -> ResumeServiceResult:
        resume = self.resumes.get_by_public_id_for_user(public_id, user_id)
        if resume is None:
            return ResumeServiceResult(False, "Resume not found.", status_code=404)

        limit_error = self._version_limit_error(user_id, resume.id)
        if limit_error:
            return limit_error

        current = self.resumes.get_current_version(resume.id, user_id)
        content = _extract_content(payload) or (current.content if current else {})
        plain_text = resume_utils.plain_text_from_content(content)
        version = ResumeVersion(
            user_id=user_id,
            resume=resume,
            version_number=self.resumes.next_version_number(resume.id),
            label=str(payload.get("label") or f"Version {self.resumes.next_version_number(resume.id)}")[:180],
            status="draft",
            template_key=str(payload.get("template_key") or (current.template_key if current else "classic"))[:80],
            content=content,
            plain_text=plain_text,
            change_summary=str(payload.get("change_summary") or "")[:500],
            created_from_version_id=current.id if current else None,
            completeness_snapshot=resume_completeness_scorer.score(content).score,
        )
        self.resumes.add(version)
        self.resumes.flush()
        if bool(payload.get("make_current", True)):
            self.resumes.set_current_version(resume.id, user_id, version)
        self._replace_sections(version, content, source="manual")
        self._record_score(version, plain_text, content)
        self._log_activity(user_id, "resume_version_created", "success", resume=resume, request_meta=request_meta)
        db.session.commit()
        return ResumeServiceResult(True, "Version created.", status_code=201, data={"version": serialize_version(version)})

    def restore_version(self, user_id: int, public_id: str, version_public_id: str, *, request_meta: dict[str, Any] | None = None) -> ResumeServiceResult:
        resume = self.resumes.get_by_public_id_for_user(public_id, user_id)
        source = self.resumes.get_version_by_public_id_for_user(version_public_id, user_id)
        if resume is None or source is None or source.resume_id != resume.id:
            return ResumeServiceResult(False, "Version not found.", status_code=404)

        limit_error = self._version_limit_error(user_id, resume.id)
        if limit_error:
            return limit_error

        restored = ResumeVersion(
            user_id=user_id,
            resume=resume,
            version_number=self.resumes.next_version_number(resume.id),
            label=f"Restored from v{source.version_number}"[:180],
            status="draft",
            template_key=source.template_key,
            content=copy.deepcopy(source.content or {}),
            plain_text=source.plain_text,
            change_summary=f"Restored from version {source.version_number}"[:500],
            created_from_version_id=source.id,
            ats_score_snapshot=source.ats_score_snapshot,
            completeness_snapshot=source.completeness_snapshot,
        )
        self.resumes.add(restored)
        self.resumes.flush()
        self.resumes.set_current_version(resume.id, user_id, restored)
        self._replace_sections(restored, restored.content, source="manual")
        self._record_score(restored, restored.plain_text or "", restored.content)
        resume.parsed_data = {"sections": restored.content}
        resume.extracted_skills = list(skill_extraction_engine.extract(restored.plain_text or "").skills)
        self._log_activity(
            user_id,
            "resume_version_restored",
            "success",
            resume=resume,
            details={"source_version": source.version_number, "new_version": restored.version_number},
            request_meta=request_meta,
        )
        db.session.commit()
        return ResumeServiceResult(True, "Version restored as a new version.", data={"version": serialize_version(restored)})

    def compare_versions(self, user_id: int, public_id: str, left_public_id: str, right_public_id: str) -> ResumeServiceResult:
        resume = self.resumes.get_by_public_id_for_user(public_id, user_id)
        left = self.resumes.get_version_by_public_id_for_user(left_public_id, user_id)
        right = self.resumes.get_version_by_public_id_for_user(right_public_id, user_id)
        if resume is None or left is None or right is None or left.resume_id != resume.id or right.resume_id != resume.id:
            return ResumeServiceResult(False, "Versions not found.", status_code=404)

        left_lines = (left.plain_text or "").splitlines()
        right_lines = (right.plain_text or "").splitlines()
        diff = list(difflib.unified_diff(left_lines, right_lines, fromfile=left.label, tofile=right.label, lineterm=""))
        return ResumeServiceResult(
            True,
            "Versions compared.",
            data={"left": serialize_version(left), "right": serialize_version(right), "diff": diff},
        )

    def export_resume(
        self,
        user_id: int,
        public_id: str,
        export_format: str,
        version_public_id: str | None = None,
        *,
        request_meta: dict[str, Any] | None = None,
    ) -> ResumeServiceResult:
        resume = self.resumes.get_by_public_id_for_user(public_id, user_id)
        if resume is None:
            return ResumeServiceResult(False, "Resume not found.", status_code=404)
        version = (
            self.resumes.get_version_by_public_id_for_user(version_public_id, user_id)
            if version_public_id
            else self.resumes.get_current_version(resume.id, user_id)
        )
        if version is None or version.resume_id != resume.id:
            return ResumeServiceResult(False, "Resume version not found.", status_code=404)

        export_format = export_format.lower()
        title = resume.title
        content = version.content or {}
        payload = {"resume": serialize_resume(resume, version), "version": serialize_version(version), "content": content}
        filename_base = _safe_filename(f"{resume.slug}_v{version.version_number}")

        if export_format == "json":
            exported = ResumeExportResult(f"{filename_base}.json", "application/json", resume_utils.build_json_export(payload))
        elif export_format == "html":
            exported = ResumeExportResult(f"{filename_base}.html", "text/html; charset=utf-8", resume_utils.build_printable_html(title, content).encode("utf-8"))
        elif export_format == "pdf":
            exported = ResumeExportResult(f"{filename_base}.pdf", "application/pdf", resume_utils.build_pdf_export(title, content))
        elif export_format == "docx":
            exported = ResumeExportResult(
                f"{filename_base}.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                resume_utils.build_docx_export(title, content),
            )
        else:
            return ResumeServiceResult(False, "Unsupported export format.", status_code=400, errors={"format": ["Use pdf, json, html, or docx."]})

        generated_path = resume_utils.store_export(
            exported.data,
            current_app.config["GENERATED_RESUME_FOLDER"],
            user_id,
            Path(exported.filename).stem,
            Path(exported.filename).suffix.lstrip("."),
        )
        self._log_activity(
            user_id,
            "resume_exported",
            "success",
            resume=resume,
            details={"format": export_format, "version": version.version_number},
            request_meta=request_meta,
        )
        db.session.commit()
        return ResumeServiceResult(
            True,
            "Resume exported.",
            data={
                "export": exported,
                "filename": exported.filename,
                "mimetype": exported.mimetype,
                "storage_path": str(generated_path),
            },
        )

    # FIX: New method to recalculate ATS scores for all resumes of a user (run once to fix existing data)
    def recalculate_ats_scores(self, user_id: int) -> ResumeServiceResult:
        resumes = self.resumes.list_for_user(user_id)
        fixed_count = 0
        for resume in resumes:
            version = self.resumes.get_current_version(resume.id, user_id)
            if version is None:
                continue
            content = version.content or {}
            plain_text = version.plain_text or resume_utils.plain_text_from_content(content)
            if not plain_text:
                continue
            self._record_score(version, plain_text, content)
            fixed_count += 1
        db.session.commit()
        return ResumeServiceResult(
            True,
            f"Recalculated ATS scores for {fixed_count} resumes.",
            data={"fixed_count": fixed_count},
        )

    def _parse_and_apply(self, resume: Resume, user_id: int) -> ResumeServiceResult:
        if not resume.storage_path or not resume.file_mime_type:
            resume.parsing_status = "failed"
            return ResumeServiceResult(False, "This resume has no uploaded file to parse.", status_code=400)

        limit_error = self._version_limit_error(user_id, resume.id)
        if limit_error:
            return limit_error

        try:
            parsed = resume_utils.parse_resume_file(resume.storage_path, resume.file_mime_type)
        except Exception as exc:
            resume.parsing_status = "failed"
            return ResumeServiceResult(False, "Resume parsing failed.", status_code=422, errors={"parser": [str(exc)]})

        content = resume_utils.content_from_sections(parsed.sections)
        completeness = resume_completeness_scorer.score(content).score
        current = self.resumes.get_current_version(resume.id, user_id)

        # FIX: Ensure parsed text is never empty; fallback to building from content
        parsed_text = parsed.text or resume_utils.plain_text_from_content(content)

        version = ResumeVersion(
            user_id=user_id,
            resume=resume,
            version_number=self.resumes.next_version_number(resume.id),
            label="Parsed Upload" if current is None else "Reparsed Upload",
            status="draft",
            template_key=current.template_key if current else "classic",
            content=content,
            plain_text=parsed_text,
            created_from_version_id=current.id if current else None,
            completeness_snapshot=completeness,
        )
        self.resumes.add(version)
        self.resumes.flush()
        self.resumes.set_current_version(resume.id, user_id, version)
        self._replace_sections(version, content, source="parser")
        self._record_score(version, parsed_text, content)
        resume.parsing_status = "parsed"
        resume.parsing_confidence = parsed.confidence
        resume.parsed_text_hash = _hash_text(parsed_text)
        resume.parsed_data = parsed.to_dict()
        resume.extracted_skills = list(parsed.skills)
        return ResumeServiceResult(
            True,
            "Resume parsed successfully.",
            data={"resume": serialize_resume(resume, version), "version": serialize_version(version), "parser": parsed.parser},
        )

    def _replace_sections(self, version: ResumeVersion, content: Mapping[str, Any], *, source: str) -> None:
        if version.id is None or version.resume_id is None:
            self.resumes.flush()
        sections: list[ResumeSection] = []
        for order, (section_key, value) in enumerate(content.items()):
            plain_text = resume_utils.plain_text_from_content({section_key: value})
            extracted = skill_extraction_engine.extract(plain_text)
            sections.append(ResumeSection(
                user_id=version.user_id,
                resume_id=version.resume_id,
                version_id=version.id,
                section_type=section_key,
                title=section_key.replace("_", " ").title(),
                sort_order=order,
                content=value if isinstance(value, dict) else {"text": value},
                plain_text=plain_text,
                extracted_keywords=list(extracted.skills),
                source=source,
                confidence_score=extracted.confidence_score,
            ))
        self.resumes.replace_sections(version.id, version.resume_id, version.user_id, sections)

    def _record_score(self, version: ResumeVersion, plain_text: str, content: Mapping[str, Any]) -> None:
        if version.id is None or version.resume_id is None:
            self.resumes.flush()

        # FIX: Ensure we always have text to score; build from content if plain_text is empty
        text = plain_text or resume_utils.plain_text_from_content(content)
        if not text:
            text = _build_text_from_content(content)

        # FIX: Also update version.plain_text if it was empty
        if not version.plain_text and text:
            version.plain_text = text

        ats = ats_scoring_engine.analyze(text, parsed_sections=content)
        completeness = resume_completeness_scorer.score(content).score
        version.ats_score_snapshot = ats.score
        version.completeness_snapshot = completeness

        score = self.resumes.get_latest_score_for_version(version.id, version.user_id)
        if score is None:
            if version.is_current:
                self.resumes.mark_scores_not_latest(version.resume_id, version.user_id)
            score = ResumeScore(
                user_id=version.user_id,
                resume_id=version.resume_id,
                version_id=version.id,
                score_type="ats",
                algorithm_version="offline-v1",
                is_latest=bool(version.is_current),
            )
            self.resumes.add(score)
        score.overall_score = ats.score
        score.keyword_score = ats.keyword_score
        score.formatting_score = ats.formatting_score
        score.experience_score = ats.experience_score
        score.skills_score = ats.skills_score
        score.education_score = ats.education_score
        score.completeness_score = completeness
        score.suggestions = list(ats.suggestions)
        score.breakdown = dict(ats.breakdown)
        score.raw_metrics = {"matched_keywords": list(ats.matched_keywords), "missing_keywords": list(ats.missing_keywords)}

    def _resume_limit_error(self, user: User) -> ResumeServiceResult | None:
        resume_limit, _ = self._plan_limits(user)
        if resume_limit and self.resumes.count_for_user(user.id) >= resume_limit:
            return ResumeServiceResult(
                False,
                f"Your plan allows up to {resume_limit} resumes.",
                status_code=403,
                errors={"plan": ["Upgrade your plan to create more resumes."]},
            )
        return None

    def _version_limit_error(self, user_id: int, resume_id: int) -> ResumeServiceResult | None:
        user = db.session.get(User, user_id)
        if user is None:
            return ResumeServiceResult(False, "User not found.", status_code=404)
        _, version_limit = self._plan_limits(user)
        if version_limit and len(self.resumes.list_versions(resume_id, user_id)) >= version_limit:
            return ResumeServiceResult(
                False,
                f"Your plan allows up to {version_limit} versions per resume.",
                status_code=403,
                errors={"plan": ["Upgrade your plan for unlimited resume versions."]},
            )
        return None

    def _plan_limits(self, user: User) -> tuple[int, int]:
        active = [
            subscription
            for subscription in user.subscriptions
            if subscription.status in {"active", "trialing"}
        ]
        plan = max(active, key=lambda item: item.updated_at).plan_type if active else "free"
        if plan in {"pro", "enterprise"}:
            return (
                int(current_app.config["PRO_PLAN_RESUME_LIMIT"]),
                int(current_app.config["PRO_PLAN_VERSION_LIMIT"]),
            )
        return (
            int(current_app.config["FREE_PLAN_RESUME_LIMIT"]),
            int(current_app.config["FREE_PLAN_VERSION_LIMIT"]),
        )

    def _unique_slug(self, user_id: int, title: str) -> str:
        base = _slugify(title) or "resume"
        slug = base[:200]
        counter = 2
        while self.resumes.slug_exists(user_id, slug):
            suffix = f"-{counter}"
            slug = f"{base[: 220 - len(suffix)]}{suffix}"
            counter += 1
        return slug

    def _log_activity(
        self,
        user_id: int,
        event_type: str,
        status: str,
        *,
        resume: Resume | None = None,
        severity: str = "info",
        details: dict[str, Any] | None = None,
        request_meta: dict[str, Any] | None = None,
    ) -> None:
        request_meta = request_meta or {}
        db.session.add(
            ActivityLog(
                actor_user_id=user_id,
                target_user_id=user_id,
                resume_id=resume.id if resume and resume.id else None,
                category="resume",
                event_type=event_type,
                severity=severity,
                status=status,
                request_id=request_meta.get("request_id"),
                remote_addr_hash=request_meta.get("remote_addr_hash"),
                user_agent_hash=request_meta.get("user_agent_hash"),
                details=details or {},
            )
        )


def serialize_resume(resume: Resume, version: ResumeVersion | None = None) -> dict[str, Any]:
    return {
        "id": resume.public_id,
        "title": resume.title,
        "slug": resume.slug,
        "source_type": resume.source_type,
        "visibility": resume.visibility,
        "original_filename": resume.original_filename,
        "file_size_bytes": resume.file_size_bytes,
        "file_mime_type": resume.file_mime_type,
        "parsing_status": resume.parsing_status,
        "parsing_confidence": resume.parsing_confidence,
        "extracted_skills": list(resume.extracted_skills or []),
        "current_version": serialize_version(version) if version else None,
        "created_at": _iso(resume.created_at),
        "updated_at": _iso(resume.updated_at),
    }


def serialize_version(version: ResumeVersion | None) -> dict[str, Any] | None:
    if version is None:
        return None
    return {
        "id": version.public_id,
        "version_number": version.version_number,
        "label": version.label,
        "status": version.status,
        "template_key": version.template_key,
        "content": version.content or {},
        "plain_text": version.plain_text,
        "change_summary": version.change_summary,
        "is_current": version.is_current,
        "ats_score_snapshot": version.ats_score_snapshot,
        "completeness_snapshot": version.completeness_snapshot,
        "created_at": _iso(version.created_at),
        "updated_at": _iso(version.updated_at),
    }


def _extract_content(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw_content = payload.get("content") or payload.get("sections") or {}
    if isinstance(raw_content, Mapping) and raw_content:
        return resume_utils.content_from_sections(raw_content)
    return {}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def _safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._") or "resume"


def _hash_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


# FIX: Helper to build text from content dict (mirrors engine helper)
def _build_text_from_content(content: Mapping[str, Any]) -> str:
    if not content:
        return ""
    parts: list[str] = []
    for key, value in content.items():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, Mapping):
            parts.extend(str(v) for v in value.values() if v is not None)
        elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            parts.extend(str(v) for v in value)
        else:
            parts.append(str(value))
    return "\n\n".join(parts)