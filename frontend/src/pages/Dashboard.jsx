import { useState, useEffect } from 'react';
import { emailApi } from '../api';

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

export default function Dashboard() {
  const [emails, setEmails] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchEmails = () => {
      emailApi.list()
        .then((data) => {
          setEmails(data);
          setLoading(false);
        })
        .catch((err) => {
          console.error("Failed to fetch emails for dashboard", err);
        });
    };

    fetchEmails();
    const interval = setInterval(fetchEmails, 5000);
    return () => clearInterval(interval);
  }, []);

  // Compute stats across all emails
  const outboundEmails = emails.filter(e => e.direction === 'outbound');
  const totalSent = outboundEmails.length;
  const totalOpened = outboundEmails.filter(e => e.open_count > 0 || e.status === 'opened' || e.status === 'clicked').length;
  const totalClicked = outboundEmails.filter(e => e.status === 'clicked').length;
  const totalBounced = outboundEmails.filter(e => e.status === 'bounced').length;

  const recent20 = emails.slice(0, 20);

  return (
    <div className="dashboard-page">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        <div className="panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
          <div className="label-text" style={{ fontSize: '0.8rem', marginBottom: '0.5rem' }}>Total Sent</div>
          <div style={{ fontSize: '2rem', fontWeight: 'bold', color: '#fff' }}>{totalSent}</div>
        </div>
        <div className="panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
          <div className="label-text" style={{ fontSize: '0.8rem', marginBottom: '0.5rem', color: '#eab308' }}>Total Opened</div>
          <div style={{ fontSize: '2rem', fontWeight: 'bold', color: '#eab308' }}>{totalOpened}</div>
        </div>
        <div className="panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
          <div className="label-text" style={{ fontSize: '0.8rem', marginBottom: '0.5rem', color: '#22c55e' }}>Total Clicked</div>
          <div style={{ fontSize: '2rem', fontWeight: 'bold', color: '#22c55e' }}>{totalClicked}</div>
        </div>
        <div className="panel" style={{ padding: '1.5rem', textAlign: 'center' }}>
          <div className="label-text" style={{ fontSize: '0.8rem', marginBottom: '0.5rem', color: '#ef4444' }}>Total Bounced</div>
          <div style={{ fontSize: '2rem', fontWeight: 'bold', color: '#ef4444' }}>{totalBounced}</div>
        </div>
      </div>

      <section className="panel">
        <div className="panel-header">
          <h2>Recent Activity (Last 20 Emails)</h2>
          <span className="live-dot" />
          <span className="live-label">Live</span>
        </div>

        {recent20.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">📭</span>
            <p>{loading ? 'Loading activity...' : 'No activity logged yet.'}</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>To</th>
                  <th>Direction</th>
                  <th>Subject</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Opens</th>
                  <th>Sent At</th>
                  <th>Opened At</th>
                </tr>
              </thead>
              <tbody>
                {recent20.map((em) => (
                  <tr key={em.id}>
                    <td className="cell-to">{em.prospect_id ? (em.status === 'bounced' ? '⚠️ ' : '') + em.subject : '—'}</td>
                    {/* Wait, the column requested: To, Subject, Status, Confidence, Opens, Sent At, Opened At. */}
                    {/* Let's lookup recipient from body or fallback. Let's make sure it matches. */}
                    <td className="cell-to" style={{ fontWeight: '500' }}>
                      {em.direction === 'inbound' ? '📥 Prospect Reply' : '📤 Outbound'}
                    </td>
                    <td className="cell-subject">{em.subject || '—'}</td>
                    <td>
                      <Badge text={em.status} colorMap={STATUS_COLORS} />
                    </td>
                    <td>
                      <Badge text={em.open_confidence} colorMap={CONFIDENCE_COLORS} />
                    </td>
                    <td className="cell-center">{em.open_count}</td>
                    <td className="cell-time">{timeAgo(em.sent_at)}</td>
                    <td className="cell-time">{timeAgo(em.opened_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
