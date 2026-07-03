import os
import re
import base64
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import resend

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "you@yourdomain.com")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

resend.api_key = RESEND_API_KEY

app = FastAPI(title="Email Open Tracking Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------
emails: dict[str, dict] = {}

# 1x1 transparent GIF
TRACKING_PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body_html: str


# ---------------------------------------------------------------------------
# POST /send-email
# ---------------------------------------------------------------------------
@app.post("/send-email")
async def send_email(payload: SendEmailRequest):
    email_id = str(uuid4())

    # Inject tracking pixel
    pixel_tag = (
        f'<img src="{BASE_URL}/track/open/{email_id}" '
        f'width="1" height="1" style="display:none" alt="" />'
    )
    body = payload.body_html
    if "</body>" in body.lower():
        body = re.sub(
            r"(</body>)", rf"{pixel_tag}\1", body, flags=re.IGNORECASE
        )
    else:
        body += pixel_tag

    # Wrap links with click tracker
    body = re.sub(
        r'href="(https?://[^"]+)"',
        lambda m: f'href="{BASE_URL}/track/click/{email_id}?url={m.group(1)}"',
        body,
    )

    try:
        resend.Emails.send(
            {
                "from": FROM_EMAIL,
                "to": payload.to,
                "subject": payload.subject,
                "html": body,
                "tags": [{"name": "email_id", "value": email_id}],
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    now = datetime.now(timezone.utc).isoformat()
    emails[email_id] = {
        "id": email_id,
        "to": payload.to,
        "subject": payload.subject,
        "body_html": body,
        "sent_at": now,
        "status": "sent",
        "open_confidence": "none",
        "pixel_fired": False,
        "is_apple_proxy": False,
        "opened_at": None,
        "clicked_at": None,
        "clicked_link": None,
        "bounce_type": None,
        "user_agent": None,
        "open_count": 0,
    }

    return {"email_id": email_id, "status": "sent"}


# ---------------------------------------------------------------------------
# GET /track/open/{email_id}
# ---------------------------------------------------------------------------
@app.get("/track/open/{email_id}")
async def track_open(email_id: str, request: Request):
    if email_id in emails:
        rec = emails[email_id]
        ua = request.headers.get("user-agent", "")
        is_apple = "Apple" in ua and "Mail" in ua
        rec["open_count"] += 1
        rec["is_apple_proxy"] = is_apple
        rec["user_agent"] = ua

        if not rec["pixel_fired"]:
            rec["pixel_fired"] = True
            rec["opened_at"] = datetime.now(timezone.utc).isoformat()
            # Only set status/confidence if not already confirmed by a click
            if rec["open_confidence"] != "confirmed":
                rec["status"] = "opened"
                rec["open_confidence"] = "uncertain" if is_apple else "likely"

    return Response(content=TRACKING_PIXEL, media_type="image/gif")


# ---------------------------------------------------------------------------
# GET /track/click/{email_id}
# ---------------------------------------------------------------------------
@app.get("/track/click/{email_id}")
async def track_click(email_id: str, url: str, request: Request):
    if email_id in emails:
        rec = emails[email_id]
        rec["clicked_at"] = datetime.now(timezone.utc).isoformat()
        rec["clicked_link"] = url
        rec["status"] = "clicked"
        rec["open_confidence"] = "confirmed"
        # If pixel never fired, still mark as opened via click
        if not rec["opened_at"]:
            rec["opened_at"] = rec["clicked_at"]
        if not rec["pixel_fired"]:
            rec["open_count"] += 1
            rec["pixel_fired"] = True

    html = f"""<html>
      <head><meta http-equiv="refresh" content="0; url={url}" /></head>
      <body>Redirecting...</body>
    </html>"""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# POST /webhook/resend
# ---------------------------------------------------------------------------
@app.post("/webhook/resend")
async def webhook_resend(request: Request):
    try:
        body = await request.json()
        print("RESEND WEBHOOK PAYLOAD:", body)
    except Exception:
        return {"ok": True}

    event_type = body.get("type", "")
    data = body.get("data", {})

    # Resend sends tags in multiple formats depending on API version
    # Handle all of them
    email_id = None
    tags = data.get("tags", [])

    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                # Format: [{"name": "email_id", "value": "..."}]
                if tag.get("name") == "email_id":
                    email_id = tag.get("value")
                    break
            elif isinstance(tag, str):
                # Format: ["email_id:abc123"]
                if tag.startswith("email_id:"):
                    email_id = tag.split(":", 1)[1]
                    break
    elif isinstance(tags, dict):
        # Format: {"email_id": "abc123"}
        email_id = tags.get("email_id")

    if not email_id or email_id not in emails:
        return {"ok": True}

    rec = emails[email_id]

    if event_type == "email.delivered":
        rec["status"] = "delivered"
    elif event_type == "email.bounced":
        rec["status"] = "bounced"
        rec["bounce_type"] = data.get("bounce", {}).get("type")
    elif event_type == "email.complained":
        rec["status"] = "spam"

    return {"ok": True}


# ---------------------------------------------------------------------------
# GET /emails
# ---------------------------------------------------------------------------
@app.get("/emails")
async def list_emails():
    return sorted(emails.values(), key=lambda e: e["sent_at"], reverse=True)


# ---------------------------------------------------------------------------
# GET /emails/{email_id}
# ---------------------------------------------------------------------------
@app.get("/emails/{email_id}")
async def get_email(email_id: str):
    if email_id not in emails:
        raise HTTPException(status_code=404, detail="Email not found")
    return emails[email_id]
