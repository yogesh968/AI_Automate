import React from 'react';
import { bridge } from '../bridge.js';
import ChatTab from './ChatTab.jsx';
import ActivityTab from './ActivityTab.jsx';
import SettingsTab from './SettingsTab.jsx';

const STATUS_TEXT = {
  idle: 'Online',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
  sleeping: 'Mic muted',
  error: 'Error',
  offline: 'Offline',
};

export default function Panel(props) {
  const { tab, setTab, onClose, engine, conn, restartEngine, orbState, hello } = props;

  let body;
  if (engine.status === 'error') {
    body = <EngineProblem engine={engine} onRetry={restartEngine} />;
  } else if (engine.status !== 'ready' || conn !== 'open') {
    body = <Booting engine={engine} conn={conn} />;
  } else if (tab === 'activity') {
    body = <ActivityTab audit={props.audit} send={props.send} />;
  } else if (tab === 'settings') {
    body = (
      <SettingsTab
        settings={props.settings}
        keys={props.keys}
        send={props.send}
        toast={props.toast}
        micMuted={props.micMuted}
        onToggleMic={props.onToggleMic}
        restartEngine={restartEngine}
      />
    );
  } else {
    body = (
      <ChatTab
        items={props.items}
        transcript={props.transcript}
        orbState={orbState}
        keys={props.keys}
        settings={props.settings}
        micMuted={props.micMuted}
        onToggleMic={props.onToggleMic}
        onSendText={props.onSendText}
        onListen={props.onListen}
        onStop={props.onStop}
        onConfirm={props.onConfirm}
        onClearChat={props.onClearChat}
        goSettings={() => setTab('settings')}
      />
    );
  }

  return (
    <section className="panel" data-hit>
      <div className="panel-scan" aria-hidden />
      <header className="panel-header">
        <div className="brand">
          <span className="brand-name">J.A.R.V.I.S.</span>
          <span className={`status-dot status-${orbState}`} />
          <span className="status-text">{STATUS_TEXT[orbState] || orbState}</span>
        </div>
        <div className="header-actions">
          {hello?.version && <span className="version">v{hello.version}</span>}
          <button className="icon-btn" title="Close (Esc)" onClick={onClose}>
            ✕
          </button>
        </div>
      </header>

      <nav className="tabs">
        {[
          ['chat', 'Chat'],
          ['activity', 'Activity'],
          ['settings', 'Settings'],
        ].map(([id, label]) => (
          <button key={id} className={`tab ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </nav>

      <div className="panel-body">{body}</div>
    </section>
  );
}

function Booting({ engine, conn }) {
  const text =
    engine.status === 'restarting'
      ? 'Engine restarted — reconnecting…'
      : engine.status === 'ready' && conn !== 'open'
        ? 'Connecting to the engine…'
        : 'Booting systems…';
  return (
    <div className="center-state">
      <div className="hud-spinner" />
      <p className="center-title">{text}</p>
      <p className="muted">First start can take a little longer while voice models load.</p>
    </div>
  );
}

function EngineProblem({ engine, onRetry }) {
  return (
    <div className="engine-problem">
      <h3>⚠ The Jarvis engine is not running</h3>
      <pre className="problem-detail">{engine.message || 'Unknown error.'}</pre>
      <div className="setup-steps">
        <p>
          <b>First-time setup</b> (Terminal, inside the project's <code>mac</code> folder):
        </p>
        <pre className="code">
{`./setup.sh
# or by hand, in mac/engine:
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt`}
        </pre>
        <p className="muted">
          Needs Python 3.12 (brew install python@3.12). The installed Jarvis.app bundles the engine, so this is only
          for development.
        </p>
      </div>
      <div className="row gap">
        <button className="btn primary" onClick={onRetry}>
          Retry
        </button>
        <button className="btn" onClick={() => bridge.openLogs()}>
          Open logs
        </button>
      </div>
    </div>
  );
}
