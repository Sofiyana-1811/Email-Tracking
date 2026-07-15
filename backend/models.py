import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Text, ForeignKey, UUID, DateTime, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base

# Utility function for current UTC time
def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    from_email: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    campaigns: Mapped[List["Campaign"]] = relationship("Campaign", back_populates="workspace", cascade="all, delete-orphan")
    prospects: Mapped[List["Prospect"]] = relationship("Prospect", back_populates="workspace", cascade="all, delete-orphan")
    emails: Mapped[List["Email"]] = relationship("Email", back_populates="workspace", cascade="all, delete-orphan")
    followups: Mapped[List["Followup"]] = relationship("Followup", back_populates="workspace", cascade="all, delete-orphan")

class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft")  # draft, active, archived, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="campaigns")
    prospects: Mapped[List["Prospect"]] = relationship("Prospect", back_populates="campaign", cascade="all, delete-orphan")
    emails: Mapped[List["Email"]] = relationship("Email", back_populates="campaign", cascade="all, delete-orphan")

class Prospect(Base):
    __tablename__ = "prospects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    custom_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, active, replied, unsubscribed, bounced
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="prospects")
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="prospects")
    emails: Mapped[List["Email"]] = relationship("Email", back_populates="prospect", cascade="all, delete-orphan")
    followups: Mapped[List["Followup"]] = relationship("Followup", back_populates="prospect", cascade="all, delete-orphan")

class Email(Base):
    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    # Optional so workspace-only sends from Phase 1 remain valid.
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True)
    prospect_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=True)
    resend_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    direction: Mapped[str] = mapped_column(String(50), nullable=False)  # outbound or inbound
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(555), nullable=True)
    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="sent")  # sent, delivered, opened, clicked, bounced, spam
    open_confidence: Mapped[str] = mapped_column(String(50), default="none")  # none, uncertain, likely, confirmed
    pixel_fired: Mapped[bool] = mapped_column(Boolean, default=False)
    is_apple_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    clicked_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bounce_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sequence_step: Mapped[int] = mapped_column(Integer, default=1)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="emails")
    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="emails")
    prospect: Mapped["Prospect"] = relationship("Prospect", back_populates="emails")
    followups_as_parent: Mapped[List["Followup"]] = relationship("Followup", back_populates="parent_email", cascade="all, delete-orphan")

    @property
    def prospect_email(self) -> Optional[str]:
        return self.prospect.email if self.prospect else None

class Followup(Base):
    __tablename__ = "followups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    prospect_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False)
    parent_email_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("emails.id", ondelete="CASCADE"), nullable=False)
    trigger: Mapped[str] = mapped_column(String(100), nullable=False)  # no_open, opened_no_click, clicked_no_reply, reply_received
    draft_subject: Mapped[Optional[str]] = mapped_column(String(555), nullable=True)
    draft_body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, approved, rejected, sent
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="followups")
    prospect: Mapped["Prospect"] = relationship("Prospect", back_populates="followups")
    parent_email: Mapped["Email"] = relationship("Email", back_populates="followups_as_parent")
