import React from 'react';

const ICON = { info: 'ℹ', reminder: '⏰', warning: '⚠', error: '✕' };

export default function Toasts({ toasts, onDismiss }) {
  if (!toasts.length) return null;
  return (
    <div className="toasts">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`} data-hit onClick={() => onDismiss(t.id)}>
          <span className="toast-icon">{ICON[t.kind] || ICON.info}</span>
          <div>
            <div className="toast-title">{t.title}</div>
            {t.body && <div className="toast-body">{t.body}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}
