# AI Outreach Platform — Phased Build Prompt

## How to Use This Prompt
This is a multi-phase build. Before starting, read ALL phases so you understand the full picture. Then execute ONE phase at a time. After each phase:
1. Create a short plan (bullet points) for what you are about to build in that phase
2. Show the plan to the user and wait for confirmation
3. Execute the plan
4. List what the user should test before moving to the next phase

Do not start the next phase until the user confirms the current phase is working.

---

## Full Stack (for context across all phases)
- **Backend:** FastAPI (async), SQLAlchemy (async), asyncpg, Resend SDK, Google Generative AI SDK, APScheduler
- **Database:** PostgreSQL via Neon (connection string in env)
- **Frontend:** React (Vite), axios, plain CSS, no TypeScript, no UI library
- **LLM:** Google Gemini 2.5 Flash via `google-generativeai` SDK

## ENV Variables (create `backend/.env` once, reuse across all phases)
```
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
RESEND_API_KEY=re_xxxx
FROM_EMAIL=you@yourdomain.com
BASE_URL=http://localhost:8000
GEMINI_API_KEY=your_gemini_key
```

---

## Project Structure (full — build incrementally across phases)
```
project/
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── crud.py
│   ├── scheduler.py
│   ├── llm.py
│   ├── tracking.py
│   ├── .env
│   └── requirements.txt
└── frontend/
    ├── package.json
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── api.js
        └── pages/
            ├── Dashboard.jsx
            ├── Campaigns.jsx
            ├── CampaignDetail.jsx
            └── ApprovalQueue.jsx
```

---

# PHASE 1 — Database + Email Tracking

## Goal
Replace the in-memory dict from the demo with a real PostgreSQL database. Get email send + tracking (open pixel + click redirect + Resend webhook) working end to end with persistent storage.

## Files to Create in Phase 1
`database.py`, `models.py`, `schemas.py`, `crud.py`, `tracking.py`, `main.py` (partial), `requirements.txt`

---

### `database.py`
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
import os

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

---

### `models.py`
Import `Base` from `database.py`. Use `Mapped` and `mapped_column`. UUID PKs use `default=uuid4`. All datetimes use `datetime.utcnow`.

**Table: `workspaces`**
`id` (UUID PK), `name` (str), `from_email` (str), `created_at` (datetime)

**Table: `emails`**
`id` (UUID PK), `workspace_id` (UUID FK → workspaces.id), `resend_message_id` (str, nullable), `direction` (str, default `"outbound"`), `to_email` (str), `subject` (str), `body_html` (Text), `status` (str, default `"sent"`), `open_confidence` (str, default `"none"`), `pixel_fired` (bool, default False), `is_apple_proxy` (bool, default False), `open_count` (int, default 0), `opened_at` (datetime, nullable), `clicked_at` (datetime, nullable), `clicked_link` (str, nullable), `bounce_type` (str, nullable), `user_agent` (str, nullable), `sent_at` (datetime, default utcnow)

Status values: `sent`, `delivered`, `opened`, `clicked`, `bounced`, `spam`
Confidence values: `none`, `uncertain`, `likely`, `confirmed`

---

### `tracking.py`
```python
import re, base64
TRACKING_PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

def inject_tracking(body_html: str, email_id: str, base_url: str) -> str:
    # Wrap all href="http..." links with click tracker
    body_html = re.sub(
        r'href="(https?://[^"]+)"',
        lambda m: f'href="{base_url}/track/click/{email_id}?url={m.group(1)}"',
        body_html
    )
    # Inject pixel before </body> or append
    pixel = f'<img src="{base_url}/track/open/{email_id}" width="1" height="1" style="display:none" alt="" />'
    if re.search(r'</body>', body_html, re.IGNORECASE):
        body_html = re.sub(r'(</body>)', rf'{pixel}\1', body_html, flags=re.IGNORECASE)
    else:
        body_html += pixel
    return body_html
```

---

### `schemas.py` (Phase 1 subset)
Pydantic v2. Use `model_config = ConfigDict(from_attributes=True)` on response schemas.

- `WorkspaceCreate`: `name: str`, `from_email: str`
- `WorkspaceResponse`: all workspace fields
- `SendEmailRequest`: `workspace_id: UUID`, `to: str`, `subject: str`, `body_html: str`
- `EmailResponse`: all email fields

---

### `crud.py` (Phase 1 subset)
Async functions only. One function per operation.

- `create_workspace(db, name, from_email) → Workspace`
- `get_workspace(db, workspace_id) → Workspace | None`
- `list_workspaces(db) → list[Workspace]`
- `create_email(db, **fields) → Email`
- `get_email_by_id(db, email_id) → Email | None`
- `update_email_fields(db, email_id, **kwargs)` — generic update, commit, refresh
- `list_emails(db, workspace_id=None) → list[Email]` — sorted by sent_at desc

---

### `main.py` (Phase 1)
FastAPI app. Lifespan creates all tables via `Base.metadata.create_all`. CORS allows all origins.

Load `.env` with `load_dotenv()` at top. Read `RESEND_API_KEY`, `FROM_EMAIL`, `BASE_URL` from env.

**Endpoints:**

`POST /workspaces` — create workspace, return WorkspaceResponse

`GET /workspaces` — list all workspaces

`POST /send-email`
- Body: `SendEmailRequest`
- Generate UUID for email_id
- Call `inject_tracking(body_html, str(email_id), BASE_URL)`
- Send via Resend:
  ```python
  resend.Emails.send({
      "from": FROM_EMAIL,
      "to": payload.to,
      "subject": payload.subject,
      "html": modified_html,
      "tags": [{"name": "email_id", "value": str(email_id)}]
  })
  ```
- Store email in DB with all defaults
- Return EmailResponse

`GET /track/open/{email_id}`
- Always return 1×1 GIF (media_type `image/gif`) — never 404
- If email found in DB:
  - Increment `open_count`
  - Check UA: `is_apple = "Apple" in ua and "Mail" in ua`
  - If `pixel_fired == False`:
    - Set `pixel_fired=True`, `opened_at=utcnow`, `status="opened"`
    - `open_confidence = "uncertain" if is_apple else "likely"`
  - Never overwrite if `open_confidence == "confirmed"`
  - Update `user_agent`, `is_apple_proxy`
  - Call `update_email_fields`

`GET /track/click/{email_id}?url=`
- If email found:
  - Set `clicked_at=utcnow`, `clicked_link=url`, `status="clicked"`, `open_confidence="confirmed"`
  - If `opened_at` is None: set `opened_at=utcnow`
  - If `pixel_fired == False`: set `pixel_fired=True`, `open_count=1`
  - Call `update_email_fields`
- Return HTMLResponse:
  ```html
  <html><head><meta http-equiv="refresh" content="0; url={url}"/></head><body>Redirecting...</body></html>
  ```

`POST /webhook/resend`
- Wrap entire body in try/except — return `{"ok": True}` on any error
- Print full payload to stdout
- Extract `email_id` from `data.tags` — handle all three formats:
  - List of dicts: `[{"name": "email_id", "value": "..."}]`
  - Dict: `{"email_id": "..."}`
  - List of strings: `["email_id:..."]`
- Map events:
  - `email.delivered` → `status="delivered"`
  - `email.bounced` → `status="bounced"`, save `bounce_type`
  - `email.complained` → `status="spam"`
- Call `update_email_fields`

`GET /emails` — list emails (optional query param `workspace_id`)

`GET /emails/{email_id}` — get single email or 404

---

### `requirements.txt`
```
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
asyncpg
resend
python-dotenv
python-multipart
pydantic[email]
```

---

## Phase 1 Frontend
Minimal single-page React app. Two panels side by side.

**Left — Compose**
- Inputs: workspace_id (text), to (email), subject, body_html (textarea, pre-filled with sample HTML containing a link)
- Button: Send Email

**Right — Email Log**
- Poll `GET /emails` every 3 seconds
- Table: To, Subject, Status (color badge), Confidence (color badge), Opens, Sent At, Opened At, Clicked Link
- Status colors: sent=gray, delivered=blue, opened=yellow, clicked=green, bounced=red, spam=orange
- Confidence colors: none=gray, uncertain=orange, likely=yellow, confirmed=green

---

## Phase 1 Tests (user runs these before moving to Phase 2)
1. Run `uvicorn main:app --reload --port 8000`
2. Open `http://localhost:8000/docs` — verify all endpoints listed
3. `POST /workspaces` with name and from_email — copy the returned `id`
4. Paste workspace_id into frontend, send an email to yourself
5. Check Neon dashboard → verify a row exists in `emails` table
6. Open the email → pixel should fire → status flips to `opened`
7. Click the link → status flips to `clicked`, confidence = `confirmed`
8. Check uvicorn logs for webhook payload print
9. Restart uvicorn → `GET /emails` should still return data (confirms persistence)

---

# PHASE 2 — Campaign & Prospect Management

## Goal
Add campaigns and prospects. Users can create a campaign, add prospects manually or via CSV, and send an initial email to a prospect from the UI.

## New Files in Phase 2
No new files — extend `models.py`, `schemas.py`, `crud.py`, `main.py`, and replace the frontend with a tabbed UI.

---

### Add to `models.py`

**Table: `campaigns`**
`id` (UUID PK), `workspace_id` (UUID FK → workspaces.id), `name` (str), `status` (str, default `"draft"`), `created_at` (datetime)

**Table: `prospects`**
`id` (UUID PK), `workspace_id` (UUID FK), `campaign_id` (UUID FK → campaigns.id), `email` (str), `name` (str, nullable), `company` (str, nullable), `role` (str, nullable), `custom_notes` (Text, nullable), `status` (str, default `"pending"`), `created_at` (datetime)

**Update `emails` table** — add columns:
`campaign_id` (UUID FK → campaigns.id, nullable), `prospect_id` (UUID FK → prospects.id, nullable), `sequence_step` (int, default 1)

---

### Add to `schemas.py`
- `CampaignCreate`: `workspace_id: UUID`, `name: str`
- `CampaignResponse`: all campaign fields + `prospect_count: int` (computed)
- `ProspectCreate`: `workspace_id: UUID`, `campaign_id: UUID`, `email: str`, `name`, `company`, `role`, `custom_notes` (all optional str)
- `ProspectResponse`: all prospect fields
- `CSVUploadResponse`: `imported: int`, `skipped: int`, `errors: list[str]`
- Update `SendEmailRequest`: add `campaign_id: UUID`, `prospect_id: UUID`

---

### Add to `crud.py`
- `create_campaign(db, workspace_id, name) → Campaign`
- `get_campaign(db, campaign_id) → Campaign | None`
- `list_campaigns(db, workspace_id) → list[Campaign]`
- `create_prospect(db, **fields) → Prospect`
- `get_prospect(db, prospect_id) → Prospect | None`
- `list_prospects(db, campaign_id) → list[Prospect]`
- `update_prospect_status(db, prospect_id, status)`
- `count_prospects(db, campaign_id) → int`
- `get_outbound_email_count(db, prospect_id) → int` — counts sent outbound emails for sequence_step calculation

---

### Add to `main.py`

**New Endpoints:**

`POST /campaigns` — create campaign

`GET /campaigns?workspace_id=` — list campaigns with prospect_count

`GET /campaigns/{campaign_id}` — single campaign

`POST /prospects` — create single prospect

`GET /prospects?campaign_id=` — list prospects

`POST /prospects/csv-upload` — `multipart/form-data` with `workspace_id`, `campaign_id`, `csv_file`
- Parse CSV using Python's built-in `csv` module
- Required column: `email`. Optional: `name`, `company`, `role`, `custom_notes`
- Skip rows: missing email, or email already exists in same campaign (check DB)
- Return `CSVUploadResponse`

**Update `POST /send-email`:**
- Accept updated `SendEmailRequest` with `campaign_id` and `prospect_id`
- After send: update prospect status to `"active"` if currently `"pending"`
- Set `sequence_step` = count of existing outbound emails for prospect + 1

---

### Phase 2 Frontend
Tabbed navigation: **Dashboard** | **Campaigns** | **Approval Queue** (queue tab empty for now)

**Dashboard tab** — same as Phase 1 email log, no changes

**Campaigns tab** — two sections:

Top: Create Campaign form (workspace_id input + name input + button)

Bottom: Campaign list. Each campaign row is clickable → shows CampaignDetail inline below the list.

**CampaignDetail** (inline, not a new page):

Section 1 — Add Prospect manually (email, name, company, role, notes inputs + button)

Section 2 — CSV Upload (file input + upload button + result message)

Section 3 — Prospect table (Email, Name, Company, Status columns). Each row has a "Send Email" button that toggles an inline compose form beneath that row with subject + body textarea + send button. Pre-fill body with:
```html
<p>Hi {prospect.name || "there"},</p>
<p>I wanted to reach out about...</p>
<p><a href="https://example.com">Learn more here</a></p>
```

---

## Phase 2 Tests
1. Restart uvicorn — Neon should auto-create new tables
2. Create a campaign via UI
3. Add 2 prospects manually
4. Upload a CSV with 3 prospects (include one duplicate to test skip logic)
5. Verify CSV result shows correct imported/skipped counts
6. Send an email to one prospect → verify prospect status changes to `"active"` in DB
7. Check `sequence_step = 1` on the email record
8. Send a second email to same prospect → verify `sequence_step = 2`

---

# PHASE 3 — LLM Follow-up Drafting + Scheduler

## Goal
Add automated follow-up evaluation. Every 6 hours, check prospects due for follow-up, determine the trigger, call Gemini to draft the email, and store it as a pending follow-up.

## New Files in Phase 3
`llm.py`, `scheduler.py`

---

### `llm.py`
```python
import google.generativeai as genai
import os, json, re

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

def format_thread(emails: list) -> str:
    parts = []
    for e in emails:
        label = "YOU SENT" if e.direction == "outbound" else "PROSPECT REPLIED"
        parts.append(f"[{label}]\nSubject: {e.subject}\n{e.body_html}")
    return "\n---\n".join(parts)

async def draft_followup(prospect, thread_emails: list, trigger: str) -> dict:
    descriptions = {
        "no_open": "Prospect never opened the email. They likely missed it.",
        "opened_no_click": "Prospect opened but did not click. Mild interest, needs nudge.",
        "clicked_no_reply": "Prospect clicked a link but never replied. Strong interest.",
        "reply_received": "Prospect replied. Draft a response to their message."
    }
    prompt = f"""You are a sales assistant drafting a follow-up email.

PROSPECT:
- Name: {prospect.name or "there"}
- Company: {prospect.company or "their company"}
- Role: {prospect.role or "unknown"}
- Notes: {prospect.custom_notes or "none"}

SITUATION: {descriptions.get(trigger, trigger)}

EMAIL THREAD:
{format_thread(thread_emails)}

RULES:
- Under 100 words in body
- Match tone to situation
- One clear CTA at the end
- body_html uses <p> tags only

Return ONLY valid JSON, no markdown, no explanation:
{{"subject": "...", "body_html": "...", "reasoning": "one sentence"}}"""

    response = model.generate_content(prompt)
    text = response.text.strip()
    text = re.sub(r'^```json|^```|```$', '', text, flags=re.MULTILINE).strip()
    return json.loads(text)
```

---

### Add to `models.py`

**Table: `followups`**
`id` (UUID PK), `workspace_id` (UUID FK), `prospect_id` (UUID FK → prospects.id), `campaign_id` (UUID FK → campaigns.id), `parent_email_id` (UUID FK → emails.id, nullable), `trigger` (str), `draft_subject` (str, nullable), `draft_body_html` (Text, nullable), `llm_reasoning` (Text, nullable), `status` (str, default `"pending"`), `scheduled_for` (datetime, nullable), `approved_at` (datetime, nullable), `sent_at` (datetime, nullable), `created_at` (datetime)

---

### Add to `crud.py`
- `create_followup(db, **fields) → Followup`
- `get_followup(db, followup_id) → Followup | None`
- `list_pending_followups(db, workspace_id) → list[Followup]` — status = "pending", include joined prospect info
- `update_followup_status(db, followup_id, status, **extra_fields)`
- `get_prospects_due_for_followup(db) → list[Prospect]`
  - Prospect status is `"active"`
  - Latest outbound email `sent_at` is > 3 days ago
  - No followup with status `"pending"` or `"sent"` already exists for this prospect
- `get_thread_emails(db, prospect_id) → list[Email]` — all emails for prospect, ordered by sent_at asc
- `has_inbound_email(db, prospect_id) → bool`

---

### `scheduler.py`
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import AsyncSessionLocal
import crud, llm
from datetime import datetime, timedelta

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('interval', hours=6)
async def evaluate_followups():
    async with AsyncSessionLocal() as db:
        prospects = await crud.get_prospects_due_for_followup(db)
        for prospect in prospects:
            thread = await crud.get_thread_emails(db, prospect.id)
            if not thread:
                continue
            latest = thread[-1]  # most recent outbound email

            # Determine trigger
            if latest.open_confidence == "none":
                trigger = "no_open"
            elif latest.open_confidence in ("likely", "uncertain"):
                has_inbound = await crud.has_inbound_email(db, prospect.id)
                trigger = "reply_received" if has_inbound else "opened_no_click"
            elif latest.open_confidence == "confirmed":
                has_inbound = await crud.has_inbound_email(db, prospect.id)
                trigger = "reply_received" if has_inbound else "clicked_no_reply"
            else:
                continue

            try:
                draft = await llm.draft_followup(prospect, thread, trigger)
                await crud.create_followup(
                    db,
                    workspace_id=prospect.workspace_id,
                    prospect_id=prospect.id,
                    campaign_id=prospect.campaign_id,
                    parent_email_id=latest.id,
                    trigger=trigger,
                    draft_subject=draft["subject"],
                    draft_body_html=draft["body_html"],
                    llm_reasoning=draft["reasoning"],
                    status="pending",
                    scheduled_for=datetime.utcnow() + timedelta(days=1)
                )
            except Exception as e:
                print(f"LLM draft failed for prospect {prospect.id}: {e}")
```

---

### Update `main.py` for Phase 3

Import and start scheduler in lifespan:
```python
from scheduler import scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    scheduler.start()
    yield
    scheduler.shutdown()
```

Add debug endpoint to manually trigger the scheduler job (for testing):
```python
@app.post("/debug/trigger-followups")
async def trigger_followups():
    from scheduler import evaluate_followups
    await evaluate_followups()
    return {"ok": True}
```

Add to `requirements.txt`:
```
apscheduler
google-generativeai
```

---

## Phase 3 Tests
1. Send an email to a prospect and wait (or manually set `sent_at` to 4 days ago in Neon console)
2. Call `POST /debug/trigger-followups`
3. Check uvicorn logs — should show LLM being called
4. Check Neon → `followups` table should have a new row with `status="pending"`
5. Verify `draft_subject`, `draft_body_html`, `llm_reasoning` are populated
6. Check `trigger` field matches what you expected (no_open / opened_no_click etc)

---

# PHASE 4 — Approval Queue

## Goal
Build the human-in-the-loop approval flow. Users review LLM-drafted follow-ups, edit if needed, and approve or reject. Approved follow-ups are sent immediately via Resend.

## No new files — extend `schemas.py`, `main.py`, and add `ApprovalQueue.jsx`

---

### Add to `schemas.py`
- `FollowupResponse`: all followup fields + nested `prospect` object (email, name, company)
- `ApproveFollowupRequest`: `edited_subject: Optional[str] = None`, `edited_body_html: Optional[str] = None`

---

### Add to `main.py`

`GET /followups/pending?workspace_id=`
- Return list of pending followups with joined prospect info
- Include `prospect.email`, `prospect.name`, `prospect.company` in each item

`POST /followups/{followup_id}/approve`
- Body: `ApproveFollowupRequest`
- Load followup from DB — 404 if not found
- Load prospect from DB
- Use `edited_subject` if provided, else `draft_subject`
- Use `edited_body_html` if provided, else `draft_body_html`
- Call `inject_tracking(body_html, new_email_id, BASE_URL)` from tracking.py
- Send via Resend (same pattern as `/send-email`)
- Create new email record: `direction="outbound"`, `campaign_id` and `prospect_id` from followup
- Update followup: `status="sent"`, `approved_at=utcnow`, `sent_at=utcnow`
- Return updated followup

`POST /followups/{followup_id}/reject`
- Set followup `status="rejected"`
- Return updated followup

---

### Phase 4 Frontend — `ApprovalQueue.jsx`

Poll `GET /followups/pending?workspace_id={DEFAULT_WS_ID}` every 10 seconds.

If no pending items: show "No pending follow-ups" message.

For each pending followup render a card:
```
┌──────────────────────────────────────────┐
│ To: prospect email          [trigger badge]│
│ Company: company name                     │
│                                           │
│ Subject:                                  │
│ [editable input — pre-filled with draft]  │
│                                           │
│ Body:                                     │
│ [editable textarea — pre-filled]          │
│                                           │
│ LLM Reasoning: italic text here           │
│                                           │
│ [Reject]          [✓ Approve & Send]     │
└──────────────────────────────────────────┘
```

- On Approve: POST edited subject and body (use current input values even if unchanged)
- On Reject: POST reject, remove card from list
- On success of either: remove card, show brief success message
- Show loading state on buttons while request is in flight

Trigger badge colors:
- `no_open` → gray
- `opened_no_click` → yellow
- `clicked_no_reply` → green
- `reply_received` → blue

---

## Phase 4 Tests
1. Trigger `POST /debug/trigger-followups` to generate a pending followup
2. Open frontend → Approval Queue tab
3. Verify the card appears with LLM-drafted subject and body
4. Edit the body text
5. Click Approve & Send
6. Check that:
   - The email arrives in the recipient inbox
   - The card disappears from the queue
   - A new row appears in the emails log
   - The followup in Neon shows `status="sent"`
7. Trigger another followup → click Reject → verify it disappears and Neon shows `status="rejected"`

---

# Notes for IDE

- Build phases sequentially — do not merge phases or build ahead
- After each phase, explicitly list what the user needs to test
- If a phase has a blocker (e.g. Gemini key not set), surface it immediately rather than skipping
- All SQLAlchemy operations must be async — never use sync session
- All UUIDs stored as native UUID type in Postgres
- Tables auto-created via `Base.metadata.create_all` on startup — no Alembic
- Print all webhook payloads to stdout for debugging
- CORS: allow all origins, all methods, all headers (MVP only)