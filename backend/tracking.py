import re
import base64
from uuid import UUID

TRACKING_PIXEL_B64 = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
TRACKING_PIXEL = base64.b64decode(TRACKING_PIXEL_B64)

def inject_tracking(body_html: str, email_id: UUID, base_url: str) -> str:
    eid = str(email_id)
    # Wrap links
    body_html = re.sub(
        r'href="(https?://[^"]+)"',
        lambda m: f'href="{base_url}/track/click/{eid}?url={m.group(1)}"',
        body_html
    )
    # Inject pixel
    pixel = f'<img src="{base_url}/track/open/{eid}" width="1" height="1" style="display:none" alt="" />'
    if re.search(r'</body>', body_html, re.IGNORECASE):
        body_html = re.sub(r'(</body>)', rf'{pixel}\1', body_html, flags=re.IGNORECASE)
    else:
        body_html += pixel
    return body_html
