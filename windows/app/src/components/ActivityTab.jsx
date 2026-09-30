import React, { useEffect, useMemo, useState } from 'react';

function fmtTime(ts) {
  if (!ts) return '';
  const d = new Date(typeof ts === 'number' ? (ts < 1e12 ? ts * 1000 : ts) : ts);
  if (Number.isNaN(d.getTime())) return String(ts);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function Entry({ e }) {
  const [open, setOpen] = useState(false);
  const ok = e.ok !== false;
  return (
    <li className={`audit-entry ${ok ? 'ok' : 'failed'}`}>
      <button className="audit-row" onClick={() => setOpen((o) => !o)}>
        <span className={`badge level-${e.level || 'auto'}`}>{e.level || 'auto'}</span>
        <span className="audit-tool">{e.tool}</span>
        <span className="audit-status">{ok ? '✓' : '✕'}</span>
        <span className="audit-time">{fmtTime(e.ts)}</span>
      </button>
      {open && (
        <div className="audit-detail">
          {e.args && Object.keys(e.args).length > 0 && (
            <pre className="code small">{JSON.stringify(e.args, null, 2)}</pre>
          )}
          {e.result !== undefined && e.result !== null && e.result !== '' && (
            <pre className="code small result">
              {typeof e.result === 'string' ? e.result : JSON.stringify(e.result, null, 2)}
            </pre>
          )}
        </div>
      )}
    </li>
  );
}

export default function ActivityTab({ audit, send }) {
  const [filter, setFilter] = useState('');
  const [onlyFailed, setOnlyFailed] = useState(false);

  const refresh = () => send({ type: 'get_audit', limit: 200 });
  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const entries = useMemo(() => {
    const list = Array.isArray(audit) ? [...audit] : [];
    list.sort((a, b) => (Number(new Date(b.ts)) || b.ts || 0) - (Number(new Date(a.ts)) || a.ts || 0));
    const f = filter.trim().toLowerCase();
    return list.filter(
      (e) =>
        (!onlyFailed || e.ok === false) &&
        (!f || `${e.tool} ${JSON.stringify(e.args || {})} ${e.result || ''}`.toLowerCase().includes(f))
    );
  }, [audit, filter, onlyFailed]);

  return (
    <div className="activity">
      <div className="activity-bar">
        <input className="input" placeholder="Filter actions…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button className="btn" onClick={refresh} title="Refresh">
          ↻
        </button>
      </div>
      <label className="switch small">
        <input type="checkbox" checked={onlyFailed} onChange={(e) => setOnlyFailed(e.target.checked)} />
        <span className="slider" />
        <span>Only failed</span>
      </label>
      {audit === null ? (
        <p className="muted center">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="muted center">No actions yet. Everything Jarvis does on your PC is recorded here.</p>
      ) : (
        <ul className="audit-list">
          {entries.map((e, i) => (
            <Entry key={`${e.ts}-${i}`} e={e} />
          ))}
        </ul>
      )}
    </div>
  );
}
