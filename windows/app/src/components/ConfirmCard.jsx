import React, { useState } from 'react';

export default function ConfirmCard({ item, onConfirm, voiceHint }) {
  const [showArgs, setShowArgs] = useState(false);

  if (item.status !== 'pending') {
    return (
      <div className={`confirm-resolved ${item.status}`}>
        {item.status === 'approved' ? '✓ Approved' : '✕ Denied'} · <code>{item.tool}</code>
      </div>
    );
  }

  const hasArgs = item.args && Object.keys(item.args).length > 0;
  return (
    <div className="confirm-card">
      <div className="confirm-head">
        <span className="confirm-icon">⚠</span>
        <span>Permission needed</span>
        <code className="confirm-tool">{item.tool}</code>
      </div>
      <p className="confirm-desc">{item.description || `Jarvis wants to run ${item.tool}.`}</p>
      {hasArgs && (
        <>
          <button className="link-btn" onClick={() => setShowArgs((s) => !s)}>
            {showArgs ? 'Hide details' : 'Show details'}
          </button>
          {showArgs && <pre className="code small">{JSON.stringify(item.args, null, 2)}</pre>}
        </>
      )}
      <div className="row gap">
        <button className="btn primary" onClick={() => onConfirm(item.id, true)}>
          Yes, do it
        </button>
        <button className="btn danger" onClick={() => onConfirm(item.id, false)}>
          No
        </button>
      </div>
      {voiceHint && <p className="muted small">Or just say “haan” / “yes” or “nahi” / “no”.</p>}
    </div>
  );
}
