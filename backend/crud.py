import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, update, and_, not_
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
import models
import schemas

# ---------------------------------------------------------------------------
# Workspace CRUD
# ---------------------------------------------------------------------------
async def create_workspace(db: AsyncSession, workspace: schemas.WorkspaceCreate) -> models.Workspace:
    db_workspace = models.Workspace(
        name=workspace.name,
        from_email=workspace.from_email
    )
    db.add(db_workspace)
    await db.commit()
    await db.refresh(db_workspace)
    return db_workspace

async def get_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> Optional[models.Workspace]:
    stmt = select(models.Workspace).filter(models.Workspace.id == workspace_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def list_workspaces(db: AsyncSession) -> List[models.Workspace]:
    stmt = select(models.Workspace)
    result = await db.execute(stmt)
    return list(result.scalars().all())

# ---------------------------------------------------------------------------
# Campaign CRUD
# ---------------------------------------------------------------------------
async def create_campaign(db: AsyncSession, campaign: schemas.CampaignCreate) -> models.Campaign:
    db_campaign = models.Campaign(
        workspace_id=campaign.workspace_id,
        name=campaign.name,
        status=campaign.status
    )
    db.add(db_campaign)
    await db.commit()
    await db.refresh(db_campaign)
    return db_campaign

async def get_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> Optional[models.Campaign]:
    stmt = select(models.Campaign).filter(models.Campaign.id == campaign_id)
    result = await db.execute(stmt)
    campaign = result.scalar_one_or_none()
    
    if campaign:
        # Load prospect count
        p_count_stmt = select(func.count(models.Prospect.id)).filter(models.Prospect.campaign_id == campaign_id)
        campaign.prospect_count = (await db.execute(p_count_stmt)).scalar() or 0
        
        # Load email stats
        sent_count_stmt = select(func.count(models.Email.id)).filter(
            models.Email.campaign_id == campaign_id,
            models.Email.direction == "outbound"
        )
        campaign.sent_count = (await db.execute(sent_count_stmt)).scalar() or 0
        
        opened_count_stmt = select(func.count(models.Email.id)).filter(
            models.Email.campaign_id == campaign_id,
            models.Email.status == "opened"
        )
        campaign.opened_count = (await db.execute(opened_count_stmt)).scalar() or 0
        
        clicked_count_stmt = select(func.count(models.Email.id)).filter(
            models.Email.campaign_id == campaign_id,
            models.Email.status == "clicked"
        )
        campaign.clicked_count = (await db.execute(clicked_count_stmt)).scalar() or 0
        
        bounced_count_stmt = select(func.count(models.Email.id)).filter(
            models.Email.campaign_id == campaign_id,
            models.Email.status == "bounced"
        )
        campaign.bounced_count = (await db.execute(bounced_count_stmt)).scalar() or 0
        
    return campaign

async def list_campaigns(db: AsyncSession, workspace_id: uuid.UUID) -> List[models.Campaign]:
    stmt = select(models.Campaign).filter(models.Campaign.workspace_id == workspace_id)
    result = await db.execute(stmt)
    campaigns = list(result.scalars().all())
    for campaign in campaigns:
        p_count_stmt = select(func.count(models.Prospect.id)).filter(models.Prospect.campaign_id == campaign.id)
        campaign.prospect_count = (await db.execute(p_count_stmt)).scalar() or 0
    return campaigns

# ---------------------------------------------------------------------------
# Prospect CRUD
# ---------------------------------------------------------------------------
async def create_prospect(db: AsyncSession, prospect: schemas.ProspectCreate) -> models.Prospect:
    db_prospect = models.Prospect(
        workspace_id=prospect.workspace_id,
        campaign_id=prospect.campaign_id,
        email=str(prospect.email),
        name=prospect.name,
        company=prospect.company,
        role=prospect.role,
        custom_notes=prospect.custom_notes
    )
    db.add(db_prospect)
    await db.commit()
    await db.refresh(db_prospect)
    return db_prospect

async def get_prospect(db: AsyncSession, prospect_id: uuid.UUID) -> Optional[models.Prospect]:
    stmt = select(models.Prospect).filter(models.Prospect.id == prospect_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_prospect_by_email_in_campaign(db: AsyncSession, email: str, campaign_id: uuid.UUID) -> Optional[models.Prospect]:
    stmt = select(models.Prospect).filter(
        models.Prospect.email == email,
        models.Prospect.campaign_id == campaign_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_prospect_by_email_in_workspace(db: AsyncSession, email: str, workspace_id: uuid.UUID) -> Optional[models.Prospect]:
    # Match against prospects in the workspace
    stmt = select(models.Prospect).filter(
        models.Prospect.email == email,
        models.Prospect.workspace_id == workspace_id
    )
    result = await db.execute(stmt)
    return result.scalars().first()  # In case of multiple campaigns, get first one

async def list_prospects(db: AsyncSession, campaign_id: uuid.UUID) -> List[models.Prospect]:
    stmt = select(models.Prospect).filter(models.Prospect.campaign_id == campaign_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def update_prospect_status(db: AsyncSession, prospect_id: uuid.UUID, status: str) -> Optional[models.Prospect]:
    stmt = update(models.Prospect).where(models.Prospect.id == prospect_id).values(status=status)
    await db.execute(stmt)
    await db.commit()
    return await get_prospect(db, prospect_id)

# ---------------------------------------------------------------------------
# Email CRUD
# ---------------------------------------------------------------------------
async def create_email(db: AsyncSession, email_data: Dict[str, Any]) -> models.Email:
    db_email = models.Email(**email_data)
    db.add(db_email)
    await db.commit()
    await db.refresh(db_email)
    return db_email

async def get_email_by_id(db: AsyncSession, email_id: uuid.UUID) -> Optional[models.Email]:
    stmt = select(models.Email).filter(models.Email.id == email_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_email_by_resend_id(db: AsyncSession, resend_message_id: str) -> Optional[models.Email]:
    stmt = select(models.Email).filter(models.Email.resend_message_id == resend_message_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def update_email_fields(db: AsyncSession, email_id: uuid.UUID, **kwargs) -> Optional[models.Email]:
    stmt = update(models.Email).where(models.Email.id == email_id).values(**kwargs)
    await db.execute(stmt)
    await db.commit()
    return await get_email_by_id(db, email_id)

async def list_emails(
    db: AsyncSession, 
    workspace_id: Optional[uuid.UUID] = None,
    campaign_id: Optional[uuid.UUID] = None, 
    prospect_id: Optional[uuid.UUID] = None
) -> List[models.Email]:
    stmt = select(models.Email)
    filters = []
    if workspace_id is not None:
        filters.append(models.Email.workspace_id == workspace_id)
    if campaign_id is not None:
        filters.append(models.Email.campaign_id == campaign_id)
    if prospect_id is not None:
        filters.append(models.Email.prospect_id == prospect_id)
    if filters:
        stmt = stmt.filter(and_(*filters))
    stmt = stmt.order_by(models.Email.sent_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def get_outbound_emails_count_for_prospect(db: AsyncSession, prospect_id: uuid.UUID) -> int:
    stmt = select(func.count(models.Email.id)).filter(
        models.Email.prospect_id == prospect_id,
        models.Email.direction == "outbound"
    )
    result = await db.execute(stmt)
    return result.scalar() or 0

# ---------------------------------------------------------------------------
# Followup CRUD
# ---------------------------------------------------------------------------
async def create_followup(db: AsyncSession, followup_data: Dict[str, Any]) -> models.Followup:
    db_followup = models.Followup(**followup_data)
    db.add(db_followup)
    await db.commit()
    await db.refresh(db_followup)
    return db_followup

async def get_followup(db: AsyncSession, followup_id: uuid.UUID) -> Optional[models.Followup]:
    stmt = select(models.Followup).options(joinedload(models.Followup.prospect)).filter(models.Followup.id == followup_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def list_pending_followups(db: AsyncSession, workspace_id: uuid.UUID) -> List[models.Followup]:
    stmt = select(models.Followup).options(joinedload(models.Followup.prospect)).filter(
        models.Followup.workspace_id == workspace_id,
        models.Followup.status == "pending"
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def update_followup_status(db: AsyncSession, followup_id: uuid.UUID, status: str, **kwargs) -> Optional[models.Followup]:
    vals = {"status": status, **kwargs}
    stmt = update(models.Followup).where(models.Followup.id == followup_id).values(**vals)
    await db.execute(stmt)
    await db.commit()
    return await get_followup(db, followup_id)

async def get_prospects_due_for_followup(db: AsyncSession, workspace_id: uuid.UUID) -> List[models.Prospect]:
    """
    Returns prospects where:
      - status is "active"
      - workspace_id is workspace_id
      - latest outbound email sent_at is > 3 days ago
      - no followup with status "pending" or "sent" already exists for that prospect
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)

    # 1. Prospects that ALREADY have a pending or sent followup (to exclude)
    followup_subq = select(models.Followup.prospect_id).filter(
        models.Followup.status.in_(["pending", "sent"])
    )
    
    # 2. Get the latest outbound email sent_at for each prospect
    # Filter for outbound emails
    latest_email_subq = select(
        models.Email.prospect_id,
        func.max(models.Email.sent_at).label("latest_sent")
    ).filter(
        models.Email.direction == "outbound"
    ).group_by(
        models.Email.prospect_id
    ).subquery()

    # 3. Main query
    stmt = select(models.Prospect).join(
        latest_email_subq, 
        models.Prospect.id == latest_email_subq.c.prospect_id
    ).filter(
        models.Prospect.workspace_id == workspace_id,
        models.Prospect.status == "active",
        not_(models.Prospect.id.in_(followup_subq)),
        latest_email_subq.c.latest_sent < cutoff
    )

    result = await db.execute(stmt)
    return list(result.scalars().all())
