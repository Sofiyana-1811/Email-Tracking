import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import AsyncSessionLocal
import models
import crud
import llm

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

@scheduler.scheduled_job('interval', hours=6)
async def evaluate_and_draft_followups():
    logger.info("Running scheduled job: evaluate_and_draft_followups")
    async with AsyncSessionLocal() as db:
        # Get all workspaces
        stmt = select(models.Workspace)
        result = await db.execute(stmt)
        workspaces = result.scalars().all()
        
        for ws in workspaces:
            # Get prospects due for follow-up in this workspace
            prospects_due = await crud.get_prospects_due_for_followup(db, ws.id)
            logger.info(f"Workspace {ws.name} ({ws.id}): Found {len(prospects_due)} prospects due for follow-up")
            
            for prospect in prospects_due:
                # Find all emails for this prospect, ordered by sent_at asc
                thread_emails = await crud.list_emails(db, prospect_id=prospect.id)
                # Sort thread emails ascending for chronological order
                thread_emails = sorted(thread_emails, key=lambda e: e.sent_at)
                
                # Get outbound emails
                outbound_emails = [e for e in thread_emails if e.direction == "outbound"]
                if not outbound_emails:
                    logger.warning(f"Prospect {prospect.email} status is active but has no outbound emails. Skipping.")
                    continue
                
                latest_outbound = outbound_emails[-1]
                
                # Determine trigger
                trigger = None
                if latest_outbound.open_confidence == "none":
                    trigger = "no_open"
                elif latest_outbound.open_confidence in ("likely", "uncertain") and not latest_outbound.clicked_at:
                    trigger = "opened_no_click"
                elif latest_outbound.open_confidence == "confirmed":
                    # Check if prospect has sent any inbound email
                    inbound_emails = [e for e in thread_emails if e.direction == "inbound"]
                    if not inbound_emails:
                        trigger = "clicked_no_reply"
                
                if not trigger:
                    logger.info(f"Could not determine follow-up trigger for prospect {prospect.email}. Skipping.")
                    continue
                
                logger.info(f"Drafting follow-up for prospect {prospect.email} with trigger '{trigger}'")
                
                try:
                    # Draft follow-up with Gemini
                    draft = await llm.draft_followup(prospect, thread_emails, trigger)
                    
                    # Create follow-up record
                    followup_data = {
                        "workspace_id": ws.id,
                        "prospect_id": prospect.id,
                        "parent_email_id": latest_outbound.id,
                        "trigger": trigger,
                        "draft_subject": draft.get("subject"),
                        "draft_body_html": draft.get("body_html"),
                        "llm_reasoning": draft.get("reasoning"),
                        "status": "pending",
                        "scheduled_for": utc_now() + timedelta(days=3),
                        "created_at": utc_now()
                    }
                    await crud.create_followup(db, followup_data)
                    logger.info(f"Successfully drafted and scheduled followup for {prospect.email}")
                except Exception as e:
                    logger.error(f"Error drafting follow-up for prospect {prospect.email}: {e}", exc_info=True)
