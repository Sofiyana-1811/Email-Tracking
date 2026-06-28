import { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const API = 'http://localhost:8000';

const STATUS_COLORS = {
  sent: '#6b7280',
  delivered: '#3b82f6',
  opened: '#eab308',
  clicked: '#22c55e',
  bounced: '#ef4444',
  spam: '#f97316',
};

const CONFIDENCE_COLORS = {
  none: '#6b7280',
  uncertain: '#f97316',
  likely: '#eab308',
  confirmed: '#22c55e',
};

function Badge({ text, colorMap }) {
  const bg = colorMap[text] || '#6b7280';
  return (
    <span className="badge" style={{ background: bg }}>
      {text}
    </span>
  );
}

function timeAgo(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString();
}

export default function App() {
  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [bodyHtml, setBodyHtml] = useState(
    '<p>Hi there! Check out our <a href="https://example.com">website</a>.</p>'
  );
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState(null);
  const [emails, setEmails] = useState([]);
  const toastTimer = useRef(null);

  // Poll emails every 3 seconds
  useEffect(() => {
    const fetch = () =>
      axios
        .get(`${API}/emails`)
        .then((r) => setEmails(r.data))
        .catch(() => {});
    fetch();
    const id = setInterval(fetch, 3000);
    return () => clearInterval(id);
  }, []);

  // Toast auto-dismiss
  useEffect(() => {
    if (toast) {
      clearTimeout(toastTimer.current);
      toastTimer.current = setTimeout(() => setToast(null), 4000);
    }
  }, [toast]);

  async function handleSend(e) {
    e.preventDefault();
    if (!to || !subject) return;
    setSending(true);
    try {
      const res = await axios.post(`${API}/send-email`, {
        to,
        subject,
        body_html: bodyHtml,
      });
      setToast({ type: 'success', msg: `Sent! ID: ${res.data.email_id}` });
      setTo('');
      setSubject('');
      setBodyHtml(
        '<p>Hi there! Check out our <a href="https://example.com">website</a>.</p>'
      );
      // Refresh immediately
      axios.get(`${API}/emails`).then((r) => setEmails(r.data));
    } catch (err) {
      setToast({
        type: 'error',
        msg: err.response?.data?.detail || 'Send failed',
      });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-icon">📧</span>
            <h1>Email Tracker</h1>
          </div>
          <p className="subtitle">
            Send emails &amp; watch open / click events in real time
          </p>
        </div>
      </header>

      {/* Toast */}
      {toast && (
        <div className={`toast toast-${toast.type}`}>
          <span>{toast.type === 'success' ? '✓' : '✕'}</span>
          <span>{toast.msg}</span>
          <button className="toast-close" onClick={() => setToast(null)}>
            ×
          </button>
        </div>
      )}

      {/* Main */}
      <main className="main">
        {/* Compose Panel */}
        <section className="panel compose-panel">
          <div className="panel-header">
            <h2>Compose</h2>
          </div>
          <form className="compose-form" onSubmit={handleSend}>
            <label>
              <span className="label-text">To</span>
              <input
                type="email"
                placeholder="recipient@example.com"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                required
              />
            </label>
            <label>
              <span className="label-text">Subject</span>
              <input
                type="text"
                placeholder="Email subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                required
              />
            </label>
            <label>
              <span className="label-text">Body (HTML)</span>
              <textarea
                rows={6}
                value={bodyHtml}
                onChange={(e) => setBodyHtml(e.target.value)}
              />
            </label>
            <button type="submit" className="send-btn" disabled={sending}>
              {sending ? (
                <span className="spinner" />
              ) : (
                <span className="send-icon">➤</span>
              )}
              {sending ? 'Sending…' : 'Send Email'}
            </button>
          </form>
        </section>

        {/* Email Log Panel */}
        <section className="panel log-panel">
          <div className="panel-header">
            <h2>Email Log</h2>
            <span className="live-dot" />
            <span className="live-label">Live</span>
          </div>

          {emails.length === 0 ? (
            <div className="empty-state">
              <span className="empty-icon">📭</span>
              <p>No emails sent yet. Compose one to get started.</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>To</th>
                    <th>Subject</th>
                    <th>Status</th>
                    <th>Confidence</th>
                    <th>Opens</th>
                    <th>Sent At</th>
                    <th>Opened At</th>
                    <th>Clicked Link</th>
                  </tr>
                </thead>
                <tbody>
                  {emails.map((em) => (
                    <tr key={em.id}>
                      <td className="cell-to">{em.to}</td>
                      <td className="cell-subject">{em.subject}</td>
                      <td>
                        <Badge text={em.status} colorMap={STATUS_COLORS} />
                      </td>
                      <td>
                        <Badge
                          text={em.open_confidence}
                          colorMap={CONFIDENCE_COLORS}
                        />
                      </td>
                      <td className="cell-center">{em.open_count}</td>
                      <td className="cell-time">{timeAgo(em.sent_at)}</td>
                      <td className="cell-time">{timeAgo(em.opened_at)}</td>
                      <td className="cell-link">
                        {em.clicked_link ? (
                          <a
                            href={em.clicked_link}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {em.clicked_link.length > 30
                              ? em.clicked_link.slice(0, 30) + '…'
                              : em.clicked_link}
                          </a>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
