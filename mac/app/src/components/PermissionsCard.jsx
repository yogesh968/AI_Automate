import React, { useEffect, useState } from 'react';
import { bridge } from '../bridge.js';

const STATUS_LABEL = {
  granted: '✓ Allowed',
  denied: 'Not allowed',
  restricted: 'Blocked by policy',
  'not-determined': 'Not asked yet',
  'ask-on-use': 'Asked per app',
  unknown: 'Unknown',
};

// macOS privacy permissions. `compact` = only show when something is missing (chat tab);
// otherwise always show the full list (settings tab).
export default function PermissionsCard({ compact = false }) {
  const [perms, setPerms] = useState([]);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    bridge.getPermissions().then((p) => setPerms(p || []));
    return bridge.onPermissions((p) => setPerms(p || []));
  }, []);

  const missing = perms.filter((p) => p.status !== 'granted' && p.status !== 'ask-on-use');
  if (compact && (missing.length === 0 || dismissed)) return null;

  const request = async (id) => {
    const next = await bridge.requestPermission(id);
    if (next) setPerms(next);
  };

  return (
    <div className={compact ? 'onboard permissions' : 'permissions'}>
      {compact && (
        <div className="key-head">
          <h3>macOS permissions</h3>
          <button className="icon-btn" title="Later" onClick={() => setDismissed(true)}>
            ✕
          </button>
        </div>
      )}
      {compact && (
        <p className="small">
          Jarvis needs these to hear you and control your Mac. Click <b>Allow</b>, switch Jarvis on in System
          Settings, then come back — this card updates by itself.
        </p>
      )}
      <ul className="perm-list">
        {(compact ? missing : perms).map((p) => (
          <li key={p.id} className={`perm perm-${p.status}`}>
            <div className="perm-text">
              <b>{p.label}</b>
              <span className="muted small">{p.why}</span>
            </div>
            <div className="perm-actions">
              <span className={`key-state ${p.status === 'granted' ? 'saved' : 'missing'}`}>
                {STATUS_LABEL[p.status] || p.status}
              </span>
              {p.status !== 'granted' && (
                <button className="btn primary small" onClick={() => request(p.id)}>
                  {p.id === 'automation' ? 'Open' : 'Allow'}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {!compact && (
        <p className="hint">
          After allowing Accessibility or Screen Recording, use “Restart engine” below so the change takes effect.
          Automation is asked the first time Jarvis controls each app (Finder, Music, Notes…).
        </p>
      )}
    </div>
  );
}
