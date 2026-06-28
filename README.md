# Email Open Tracking Demo

A working demo of email open tracking with a **FastAPI** backend and **React** frontend. Sends real emails via [Resend](https://resend.com), injects a 1×1 tracking pixel, wraps links with a click-tracking redirect, and shows statuses updating in real time.

> **Note:** All state lives in an in-memory Python dict — it resets on server restart. This is intentional for a demo.

---

## Project Structure

```
project/
├── backend/
│   ├── main.py            # FastAPI server
│   ├── .env               # API keys & config
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       └── index.css
└── README.md
```

---

## Setup

### 1. Configure Environment

Edit `backend/.env` and fill in your Resend API key and verified sender:

```env
RESEND_API_KEY=re_xxxxxxxxxx
FROM_EMAIL=you@yourdomain.com
BASE_URL=http://localhost:8000
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at **http://localhost:5173** and the backend at **http://localhost:8000**.

---

## How It Works

1. **Compose & Send** — Fill in a recipient, subject, and HTML body. The backend injects a tracking pixel and rewrites links before sending via Resend.
2. **Open Tracking** — When the recipient's email client loads the 1×1 pixel image, the backend records the open event, timestamp, user-agent, and whether it came through Apple's privacy proxy.
3. **Click Tracking** — Links in the email redirect through the backend first, recording the click before forwarding to the real URL. A click is treated as a *confirmed* open.
4. **Webhook** — Resend can POST delivery/bounce/spam events to `POST /webhook/resend`. Configure this in your Resend dashboard if desired.
5. **Live Dashboard** — The React frontend polls `GET /emails` every 3 seconds and shows color-coded status badges updating in real time.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/send-email` | Send an email (body: `to`, `subject`, `body_html`) |
| GET | `/track/open/{email_id}` | Tracking pixel endpoint (returns 1×1 GIF) |
| GET | `/track/click/{email_id}?url=` | Click tracker (302 redirect) |
| POST | `/webhook/resend` | Resend webhook receiver |
| GET | `/emails` | List all emails (sorted newest first) |
| GET | `/emails/{email_id}` | Get single email details |

---

## Status Badges

| Status | Meaning |
|--------|---------|
| `sent` | Email handed to Resend |
| `delivered` | Resend confirmed delivery |
| `opened` | Tracking pixel was loaded |
| `clicked` | A tracked link was clicked |
| `bounced` | Delivery failed |
| `spam` | Marked as spam |

## Confidence Levels

| Level | Meaning |
|-------|---------|
| `none` | No open signal |
| `uncertain` | Opened via Apple Mail proxy (may be automated) |
| `likely` | Pixel fired from non-proxy client |
| `confirmed` | Recipient clicked a link |
