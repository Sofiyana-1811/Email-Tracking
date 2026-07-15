import os
import re
import csv
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Depends, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv
import resend

from database import engine, Base, AsyncSessionLocal
import models
import schemas
import crud
import tracking
import llm
from scheduler import scheduler

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "you@yourdomain.com")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

resend.api_key = RESEND_API_KEY

def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def extract_email(from_str: str) -> str:
    if not from_str:
        return ""
    match = re.search(r'[\w\.-]+@[\w\.-]+', from_str)
    return match.group(0).lower() if match else from_str.strip().lower()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # `create_all` does not alter existing tables. Keep databases created by
        # the later campaign phases compatible with Phase 1 workspace-only sends.
        await conn.execute(text("ALTER TABLE emails ADD COLUMN IF NOT EXISTS to_email VARCHAR(255)"))
        await conn.execute(text("ALTER TABLE emails ALTER COLUMN campaign_id DROP NOT NULL"))
        await conn.execute(text("ALTER TABLE emails ALTER COLUMN prospect_id DROP NOT NULL"))
        await conn.execute(text("""
            UPDATE emails AS email
            SET to_email = prospect.email
            FROM prospects AS prospect
            WHERE email.prospect_id = prospect.id AND email.to_email IS NULL
        """))
    # Start background scheduler
    scheduler.start()
    logger.info("Scheduler started successfully")
    yield
    # Shutdown scheduler
    scheduler.shutdown()
    logger.info("Scheduler shut down successfully")

app = FastAPI(title="AI Outreach Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db_dep():
    async with AsyncSessionLocal() as session:
        yield session

# ---------------------------------------------------------------------------
# Workspace Endpoints
# ---------------------------------------------------------------------------
@app.post("/workspaces", response_model=schemas.WorkspaceResponse)
async def create_workspace(workspace: schemas.WorkspaceCreate, db: AsyncSession = Depends(get_db_dep)):
    return await crud.create_workspace(db, workspace)

@app.get("/workspaces", response_model=List[schemas.WorkspaceResponse])
async def list_workspaces(db: AsyncSession = Depends(get_db_dep)):
    return await crud.list_workspaces(db)

# ---------------------------------------------------------------------------
# Campaign Endpoints
# ---------------------------------------------------------------------------
@app.post("/campaigns", response_model=schemas.CampaignResponse)
async def create_campaign(campaign: schemas.CampaignCreate, db: AsyncSession = Depends(get_db_dep)):
    return await crud.create_campaign(db, campaign)

@app.get("/campaigns", response_model=List[schemas.CampaignResponse])
async def list_campaigns(workspace_id: uuid.UUID, db: AsyncSession = Depends(get_db_dep)):
    return await crud.list_campaigns(db, workspace_id)

@app.get("/campaigns/{campaign_id}", response_model=schemas.CampaignResponse)
async def get_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db_dep)):
    db_campaign = await crud.get_campaign(db, campaign_id)
    if not db_campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return db_campaign

# ---------------------------------------------------------------------------
# Prospect Endpoints
# ---------------------------------------------------------------------------
@app.post("/prospects", response_model=schemas.ProspectResponse)
async def create_prospect(prospect: schemas.ProspectCreate, db: AsyncSession = Depends(get_db_dep)):
    # Check if duplicate in same campaign
    existing = await crud.get_prospect_by_email_in_campaign(db, str(prospect.email), prospect.campaign_id)
    if existing:
        raise HTTPException(status_code=400, detail="Prospect with this email already exists in campaign")
    return await crud.create_prospect(db, prospect)

@app.get("/prospects", response_model=List[schemas.ProspectResponse])
async def list_prospects(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db_dep)):
    return await crud.list_prospects(db, campaign_id)

@app.post("/prospects/csv-upload", response_model=schemas.CSVUploadResponse)
async def csv_upload(
    workspace_id: uuid.UUID = Form(...),
    campaign_id: uuid.UUID = Form(...),
    csv_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_dep)
):
    try:
        content = await csv_file.read()
        decoded = content.decode('utf-8-sig') # Use utf-8-sig to strip BOM if present
    except Exception as e:
        return schemas.CSVUploadResponse(imported=0, skipped=0, errors=[f"Failed to read file: {str(e)}"])
    
    # Get existing prospects in campaign to avoid duplicates
    existing_prospects = await crud.list_prospects(db, campaign_id)
    existing_emails = {p.email.strip().lower() for p in existing_prospects}
    
    reader = csv.DictReader(decoded.splitlines())
    imported = 0
    skipped = 0
    errors = []
    
    # Normalize headers
    if not reader.fieldnames:
        return schemas.CSVUploadResponse(imported=0, skipped=0, errors=["Empty CSV header row"])
        
    headers_map = {h.strip().lower(): h for h in reader.fieldnames}
    
    email_key = next((headers_map[k] for k in ["email", "mail", "prospect email"] if k in headers_map), None)
    name_key = next((headers_map[k] for k in ["name", "full name", "first name"] if k in headers_map), None)
    company_key = next((headers_map[k] for k in ["company", "organization", "firm"] if k in headers_map), None)
    role_key = next((headers_map[k] for k in ["role", "job title", "title"] if k in headers_map), None)
    notes_key = next((headers_map[k] for k in ["custom_notes", "notes", "description"] if k in headers_map), None)
    
    if not email_key:
        return schemas.CSVUploadResponse(imported=0, skipped=0, errors=["Required column 'email' not found in CSV"])
        
    seen_in_csv = set()
    
    for row_idx, row in enumerate(reader, start=2):
        email_val = row.get(email_key, "").strip()
        if not email_val:
            skipped += 1
            errors.append(f"Row {row_idx}: Missing email address")
            continue
            
        clean_email = email_val.lower()
        if clean_email in existing_emails or clean_email in seen_in_csv:
            skipped += 1
            # Check if duplicate in same campaign
            errors.append(f"Row {row_idx}: Duplicate email '{email_val}' skipped")
            continue
            
        name_val = row.get(name_key, "").strip() if name_key else None
        company_val = row.get(company_key, "").strip() if company_key else None
        role_val = row.get(role_key, "").strip() if role_key else None
        notes_val = row.get(notes_key, "").strip() if notes_key else None
        
        try:
            p_data = schemas.ProspectCreate(
                workspace_id=workspace_id,
                campaign_id=campaign_id,
                email=clean_email,
                name=name_val or None,
                company=company_val or None,
                role=role_val or None,
                custom_notes=notes_val or None
            )
            await crud.create_prospect(db, p_data)
            seen_in_csv.add(clean_email)
            imported += 1
        except Exception as err:
            skipped += 1
            errors.append(f"Row {row_idx}: Validation error: {str(err)}")
            
    return schemas.CSVUploadResponse(imported=imported, skipped=skipped, errors=errors)

# ---------------------------------------------------------------------------
# Send Email Endpoint
# ---------------------------------------------------------------------------
@app.post("/send-email", response_model=schemas.EmailResponse)
async def send_email(payload: schemas.SendEmailRequest, db: AsyncSession = Depends(get_db_dep)):
    workspace = await crud.get_workspace(db, payload.workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    prospect = None
    recipient = str(payload.to)
    if payload.prospect_id:
        prospect = await crud.get_prospect(db, payload.prospect_id)
        if not prospect:
            raise HTTPException(status_code=404, detail="Prospect not found")
        if prospect.workspace_id != payload.workspace_id:
            raise HTTPException(status_code=400, detail="Prospect does not belong to this workspace")
        if payload.campaign_id and prospect.campaign_id != payload.campaign_id:
            raise HTTPException(status_code=400, detail="Prospect does not belong to this campaign")
        recipient = prospect.email
    elif payload.campaign_id:
        campaign = await crud.get_campaign(db, payload.campaign_id)
        if not campaign or campaign.workspace_id != payload.workspace_id:
            raise HTTPException(status_code=400, detail="Campaign does not belong to this workspace")
        
    email_id = uuid.uuid4()
    modified_html = tracking.inject_tracking(payload.body_html, email_id, BASE_URL)
    
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": recipient,
            "subject": payload.subject,
            "html": modified_html,
            "tags": [{"name": "email_id", "value": str(email_id)}]
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send email via Resend: {str(exc)}")
        
    # Get sequence step
    seq = await crud.get_outbound_emails_count_for_prospect(db, prospect.id) + 1 if prospect else 1
    
    email_rec = {
        "id": email_id,
        "workspace_id": payload.workspace_id,
        "campaign_id": payload.campaign_id,
        "prospect_id": payload.prospect_id,
        "direction": "outbound",
        "to_email": recipient,
        "subject": payload.subject,
        "body_html": modified_html,
        "status": "sent",
        "open_confidence": "none",
        "pixel_fired": False,
        "is_apple_proxy": False,
        "open_count": 0,
        "sequence_step": seq,
        "sent_at": utc_now()
    }
    
    created_email = await crud.create_email(db, email_rec)
    
    if prospect and prospect.status == "pending":
        await crud.update_prospect_status(db, prospect.id, "active")
        
    return created_email

# ---------------------------------------------------------------------------
# Tracking (Open Pixel)
# ---------------------------------------------------------------------------
@app.get("/track/open/{email_id}")
async def track_open(email_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db_dep)):
    email_rec = await crud.get_email_by_id(db, email_id)
    if email_rec:
        ua = request.headers.get("user-agent", "")
        is_apple = "Apple" in ua and "Mail" in ua
        
        updates = {
            "open_count": email_rec.open_count + 1,
            "user_agent": ua,
            "is_apple_proxy": is_apple
        }
        
        if not email_rec.pixel_fired:
            updates["pixel_fired"] = True
            updates["opened_at"] = utc_now()
            
            # Avoid downgrading confirmed click status
            if email_rec.open_confidence != "confirmed":
                updates["status"] = "opened"
                updates["open_confidence"] = "uncertain" if is_apple else "likely"
                
        await crud.update_email_fields(db, email_id, **updates)
        
    return Response(content=tracking.TRACKING_PIXEL, media_type="image/gif")

# ---------------------------------------------------------------------------
# Tracking (Click Redirect)
# ---------------------------------------------------------------------------
@app.get("/track/click/{email_id}", response_class=HTMLResponse)
async def track_click(email_id: uuid.UUID, url: str, db: AsyncSession = Depends(get_db_dep)):
    email_rec = await crud.get_email_by_id(db, email_id)
    if email_rec:
        now = utc_now()
        updates = {
            "clicked_at": now,
            "clicked_link": url,
            "status": "clicked",
            "open_confidence": "confirmed"
        }
        
        if not email_rec.opened_at:
            updates["opened_at"] = now
            
        if not email_rec.pixel_fired:
            updates["pixel_fired"] = True
            updates["open_count"] = 1
            
        await crud.update_email_fields(db, email_id, **updates)
        
    html = f'<html><head><meta http-equiv="refresh" content="0; url={url}" /></head><body>Redirecting...</body></html>'
    return HTMLResponse(content=html)

# ---------------------------------------------------------------------------
# Resend Status Webhook
# ---------------------------------------------------------------------------
@app.post("/webhook/resend")
async def webhook_resend(request: Request, db: AsyncSession = Depends(get_db_dep)):
    try:
        body = await request.json()
        print("RESEND WEBHOOK PAYLOAD:", body)
    except Exception:
        # Wrap in try/except, return ok on any parse error
        return {"ok": True}
        
    event_type = body.get("type", "")
    data = body.get("data", {})
    
    # Extract tags - support all three formats
    email_id = None
    tags = data.get("tags", [])
    
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                if tag.get("name") == "email_id":
                    email_id = tag.get("value")
                    break
            elif isinstance(tag, str):
                if tag.startswith("email_id:"):
                    email_id = tag.split(":", 1)[1]
                    break
    elif isinstance(tags, dict):
        email_id = tags.get("email_id")
        
    if not email_id:
        return {"ok": True}
        
    try:
        email_uuid = uuid.UUID(email_id)
    except ValueError:
        return {"ok": True}
        
    email_rec = await crud.get_email_by_id(db, email_uuid)
    if not email_rec:
        return {"ok": True}
        
    updates = {}
    if event_type == "email.delivered":
        updates["status"] = "delivered"
    elif event_type == "email.bounced":
        updates["status"] = "bounced"
        updates["bounce_type"] = data.get("bounce", {}).get("type")
        # Update prospect status to bounced
        await crud.update_prospect_status(db, email_rec.prospect_id, "bounced")
    elif event_type == "email.complained":
        updates["status"] = "spam"
        
    if updates:
        await crud.update_email_fields(db, email_uuid, **updates)
        
    return {"ok": True}

# ---------------------------------------------------------------------------
# Inbound Email Webhook
# ---------------------------------------------------------------------------
@app.post("/webhook/resend/inbound")
async def webhook_resend_inbound(request: Request, db: AsyncSession = Depends(get_db_dep)):
    try:
        body = await request.json()
        print("INBOUND WEBHOOK PAYLOAD:", body)
    except Exception:
        return {"ok": True}
        
    # Extract payload structure from Resend inbound payload
    # Resend inbound schema holds information directly or inside a wrapper
    from_field = body.get("from") or body.get("data", {}).get("from", "")
    subject = body.get("subject") or body.get("data", {}).get("subject", "")
    html_body = body.get("html") or body.get("data", {}).get("html", "")
    text_body = body.get("text") or body.get("data", {}).get("text", "")
    
    from_email = extract_email(from_field)
    if not from_email:
        return {"ok": True}
        
    # Look up prospect by email in prospects table
    # We find it by matching against prospect email
    stmt = select(models.Prospect).filter(models.Prospect.email == from_email)
    res = await db.execute(stmt)
    prospect = res.scalars().first()
    
    if prospect:
        # Create inbound email record
        email_data = {
            "id": uuid.uuid4(),
            "workspace_id": prospect.workspace_id,
            "campaign_id": prospect.campaign_id,
            "prospect_id": prospect.id,
            "direction": "inbound",
            "to_email": FROM_EMAIL,
            "subject": subject,
            "body_html": html_body or text_body,
            "status": "delivered",
            "open_confidence": "confirmed",
            "pixel_fired": True,
            "open_count": 1,
            "sent_at": utc_now()
        }
        await crud.create_email(db, email_data)
        
        # Update prospect status to replied
        await crud.update_prospect_status(db, prospect.id, "replied")
        
        # Get thread emails for Gemini context
        thread = await crud.list_emails(db, prospect_id=prospect.id)
        thread = sorted(thread, key=lambda e: e.sent_at)
        
        try:
            # Generate follow-up reply draft using LLM
            draft = await llm.draft_followup(prospect, thread, "reply_received")
            
            # Save into pending follow-ups queue
            followup_data = {
                "workspace_id": prospect.workspace_id,
                "prospect_id": prospect.id,
                "parent_email_id": email_data["id"],
                "trigger": "reply_received",
                "draft_subject": draft.get("subject"),
                "draft_body_html": draft.get("body_html"),
                "llm_reasoning": draft.get("reasoning"),
                "status": "pending",
                "scheduled_for": utc_now() + timedelta(days=3),
                "created_at": utc_now()
            }
            await crud.create_followup(db, followup_data)
        except Exception as exc:
            logger.error(f"Error drafting follow-up reply for {prospect.email}: {exc}", exc_info=True)
            
    return {"ok": True}

# ---------------------------------------------------------------------------
# Follow-up Approval Queue Endpoints
# ---------------------------------------------------------------------------
@app.get("/followups/pending", response_model=List[schemas.FollowupResponse])
async def list_pending_followups(workspace_id: uuid.UUID, db: AsyncSession = Depends(get_db_dep)):
    return await crud.list_pending_followups(db, workspace_id)

@app.post("/followups/{followup_id}/approve", response_model=schemas.FollowupResponse)
async def approve_followup(
    followup_id: uuid.UUID, 
    payload: schemas.ApproveFollowupRequest, 
    db: AsyncSession = Depends(get_db_dep)
):
    followup = await crud.get_followup(db, followup_id)
    if not followup:
        raise HTTPException(status_code=404, detail="Followup not found")
        
    if followup.status != "pending":
        raise HTTPException(status_code=400, detail="Followup is not in pending state")
        
    prospect = followup.prospect
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found for followup")
        
    subject = payload.edited_subject if payload.edited_subject else followup.draft_subject
    body_html = payload.edited_body_html if payload.edited_body_html else followup.draft_body_html
    
    email_id = uuid.uuid4()
    modified_html = tracking.inject_tracking(body_html, email_id, BASE_URL)
    
    try:
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": prospect.email,
            "subject": subject,
            "html": modified_html,
            "tags": [{"name": "email_id", "value": str(email_id)}]
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send followup via Resend: {str(exc)}")
        
    seq = await crud.get_outbound_emails_count_for_prospect(db, prospect.id) + 1
    
    email_rec = {
        "id": email_id,
        "workspace_id": followup.workspace_id,
        "campaign_id": prospect.campaign_id,
        "prospect_id": prospect.id,
        "direction": "outbound",
        "to_email": prospect.email,
        "subject": subject,
        "body_html": modified_html,
        "status": "sent",
        "open_confidence": "none",
        "pixel_fired": False,
        "is_apple_proxy": False,
        "open_count": 0,
        "sequence_step": seq,
        "sent_at": utc_now()
    }
    await crud.create_email(db, email_rec)
    
    # Update prospect status to active (if not already active or replied)
    if prospect.status in ("pending", "replied"):
        await crud.update_prospect_status(db, prospect.id, "active")
        
    # Update followup record
    updated_followup = await crud.update_followup_status(
        db, 
        followup_id, 
        status="sent", 
        approved_at=utc_now(), 
        sent_at=utc_now()
    )
    return updated_followup

@app.post("/followups/{followup_id}/reject", response_model=schemas.FollowupResponse)
async def reject_followup(followup_id: uuid.UUID, db: AsyncSession = Depends(get_db_dep)):
    followup = await crud.get_followup(db, followup_id)
    if not followup:
        raise HTTPException(status_code=404, detail="Followup not found")
        
    return await crud.update_followup_status(db, followup_id, status="rejected")

# ---------------------------------------------------------------------------
# Email Log Endpoints
# ---------------------------------------------------------------------------
@app.get("/emails", response_model=List[schemas.EmailResponse])
async def list_emails(
    workspace_id: Optional[uuid.UUID] = None,
    campaign_id: Optional[uuid.UUID] = None, 
    prospect_id: Optional[uuid.UUID] = None, 
    db: AsyncSession = Depends(get_db_dep)
):
    return await crud.list_emails(db, workspace_id, campaign_id, prospect_id)

@app.get("/emails/{email_id}", response_model=schemas.EmailResponse)
async def get_email(email_id: uuid.UUID, db: AsyncSession = Depends(get_db_dep)):
    email_rec = await crud.get_email_by_id(db, email_id)
    if not email_rec:
        raise HTTPException(status_code=404, detail="Email not found")
    return email_rec
