import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr

# Workspace schemas
class WorkspaceCreate(BaseModel):
    name: str
    from_email: str

class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    from_email: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Campaign schemas
class CampaignCreate(BaseModel):
    workspace_id: uuid.UUID
    name: str
    status: Optional[str] = "draft"

class CampaignResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    status: str
    created_at: datetime
    
    # Optional aggregate stats for detailed responses
    prospect_count: Optional[int] = None
    sent_count: Optional[int] = None
    opened_count: Optional[int] = None
    clicked_count: Optional[int] = None
    bounced_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

# Prospect schemas
class ProspectCreate(BaseModel):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    email: EmailStr
    name: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    custom_notes: Optional[str] = None

class ProspectResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    email: str
    name: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    custom_notes: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Email schemas
class SendEmailRequest(BaseModel):
    workspace_id: uuid.UUID
    to: EmailStr
    subject: str
    body_html: str
    campaign_id: Optional[uuid.UUID] = None
    prospect_id: Optional[uuid.UUID] = None

class EmailResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    campaign_id: Optional[uuid.UUID] = None
    prospect_id: Optional[uuid.UUID] = None
    resend_message_id: Optional[str] = None
    direction: str
    to_email: str
    subject: Optional[str] = None
    body_html: Optional[str] = None
    status: str
    open_confidence: str
    pixel_fired: bool
    is_apple_proxy: bool
    open_count: int
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    clicked_link: Optional[str] = None
    bounce_type: Optional[str] = None
    user_agent: Optional[str] = None
    sequence_step: int
    sent_at: datetime
    prospect_email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Follow-up schemas
class FollowupResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    prospect_id: uuid.UUID
    parent_email_id: uuid.UUID
    trigger: str
    draft_subject: Optional[str] = None
    draft_body_html: Optional[str] = None
    llm_reasoning: Optional[str] = None
    status: str
    scheduled_for: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
    
    # Optional prospect data joined for the approval queue UI
    prospect: Optional[ProspectResponse] = None

    model_config = ConfigDict(from_attributes=True)

class ApproveFollowupRequest(BaseModel):
    edited_subject: Optional[str] = None
    edited_body_html: Optional[str] = None

# CSV Upload Schema
class CSVUploadResponse(BaseModel):
    imported: int
    skipped: int
    errors: List[str]
