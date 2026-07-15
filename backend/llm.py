import google.generativeai as genai
import os
import json
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configure the SDK
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-2.5-flash")

def format_thread(emails: list) -> str:
    lines = []
    for e in emails:
        direction = "YOU SENT" if e.direction == "outbound" else "PROSPECT REPLIED"
        # Format dates nicely
        sent_str = e.sent_at.isoformat() if hasattr(e.sent_at, "isoformat") else str(e.sent_at)
        lines.append(f"[{direction} — {sent_str}]\nSubject: {e.subject}\n{e.body_html}\n")
    return "\n---\n".join(lines)

async def draft_followup(prospect, thread_emails: list, trigger: str) -> dict:
    trigger_descriptions = {
        "no_open": "Prospect never opened the email. They may not have seen it.",
        "opened_no_click": "Prospect opened the email but did not click any link. Mild interest.",
        "clicked_no_reply": "Prospect clicked a link but did not reply. Strong interest signal.",
        "reply_received": "Prospect replied to the email. Draft an appropriate response to their reply."
    }

    prompt = f"""You are a sales assistant drafting a follow-up email for an outreach campaign.

PROSPECT:
- Name: {prospect.name or "there"}
- Company: {prospect.company or "their company"}
- Role: {prospect.role or "unknown"}
- Notes: {prospect.custom_notes or "none"}

SITUATION: {trigger_descriptions.get(trigger, trigger)}

EMAIL THREAD SO FAR:
{format_thread(thread_emails)}

INSTRUCTIONS:
- Write a short follow-up (under 100 words body text)
- Match tone to situation: softer for no_open, curious for opened_no_click, direct for clicked_no_reply, responsive for reply_received
- End with exactly one clear CTA
- Do not be pushy or desperate
- body_html should be valid HTML with <p> tags only, no complex formatting

Respond ONLY with valid JSON, no markdown fences, no preamble:
{{"subject": "...", "body_html": "...", "reasoning": "one sentence explaining your approach"}}"""

    # genai generate_content is synchronous in the current SDK, so we run it directly or wrap it if needed.
    # Since we are async, calling it directly is fine as it's quick, but let's do a safe call.
    response = model.generate_content(prompt)
    text = response.text.strip()
    
    # Strip markdown code blocks if the LLM outputted them despite instructions
    text = re.sub(r'^```json|^```|```$', '', text, flags=re.MULTILINE).strip()
    
    return json.loads(text)
