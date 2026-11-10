from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

J = JSON().with_variant(JSONB(), "postgresql")


def uid() -> str:
    return str(uuid.uuid4())


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(200), default="")
    # workspace owner's own branding / title-block details
    firm_name: Mapped[str] = mapped_column(String(200), default="")
    firm_line: Mapped[str] = mapped_column(String(300), default="")
    logo_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|archived
    brief: Mapped[dict] = mapped_column(J, default=dict)
    client: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(String(400), default="")
    review_status: Mapped[str] = mapped_column(String(40), default="concept_unreviewed")
    current_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_good_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    use_assumptions: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Revision(Base):
    __tablename__ = "revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text, default="")
    changes: Mapped[list] = mapped_column(J, default=list)
    model: Mapped[dict] = mapped_column(J)      # immutable snapshot
    brief: Mapped[dict] = mapped_column(J)
    sheet_sigs: Mapped[dict] = mapped_column(J, default=dict)    # sheet_id -> signature
    sheet_revs: Mapped[dict] = mapped_column(J, default=dict)    # sheet number -> revision label
    render_status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|failed
    render_error: Mapped[str] = mapped_column(Text, default="")
    validation: Mapped[list] = mapped_column(J, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("project_id", "number", name="uq_revision_number"),)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))   # user|assistant|system
    content: Mapped[str] = mapped_column(Text, default="")
    events: Mapped[list] = mapped_column(J, default=list)   # structured operation results shown under the message
    status: Mapped[str] = mapped_column(String(20), default="done")  # done|error|cancelled
    attachment_ids: Mapped[list] = mapped_column(J, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(300))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Proposal(Base):
    """A pending change (edit or alternative layouts) awaiting the user's confirmation."""
    __tablename__ = "proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))      # edit|options
    base_revision_id: Mapped[str] = mapped_column(String(36))
    ops: Mapped[list] = mapped_column(J, default=list)
    preserve: Mapped[list] = mapped_column(J, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    changes: Mapped[list] = mapped_column(J, default=list)
    affected_sheets: Mapped[list] = mapped_column(J, default=list)
    options: Mapped[list] = mapped_column(J, default=list)   # for kind=options: [{label, ops, dims, changes}]
    issues: Mapped[list] = mapped_column(J, default=list)
    state: Mapped[str] = mapped_column(String(20), default="pending")  # pending|confirmed|rejected|stale
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))       # render|export
    revision_id: Mapped[str] = mapped_column(String(36), index=True)
    key: Mapped[str] = mapped_column(String(64))         # idempotency key
    params: Mapped[dict] = mapped_column(J, default=dict)
    state: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|running|done|failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    step: Mapped[str] = mapped_column(String(200), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    error_detail: Mapped[dict] = mapped_column(J, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    __table_args__ = (UniqueConstraint("project_id", "kind", "key", name="uq_job_idem"),)


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str] = mapped_column(String(36), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(10))       # svg|png|pdf|dxf
    purpose: Mapped[str] = mapped_column(String(20), default="preview")   # preview|export
    sheet_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(300), default="")
    storage_key: Mapped[str] = mapped_column(String(500))
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    meta: Mapped[dict] = mapped_column(J, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (Index("ix_artifact_rev_sheet", "revision_id", "sheet_id", "kind", "purpose"),)


class AIUsage(Base):
    __tablename__ = "ai_usage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider: Mapped[str] = mapped_column(String(20))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
