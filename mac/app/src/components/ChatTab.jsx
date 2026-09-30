import React, { useEffect, useRef, useState } from 'react';
import ConfirmCard from './ConfirmCard.jsx';
import PermissionsCard from './PermissionsCard.jsx';

const TOOL_ICON = { running: '◌', ok: '✓', failed: '✕' };

// Turns URLs into links; everything else stays plain text.
function Linkified({ text }) {
  const parts = String(text || '').split(/(https?:\/\/[^\s)]+)/g);
  return parts.map((p, i) =>
    /^https?:\/\//.test(p) ? (
      <a key={i} href={p} target="_blank" rel="noreferrer">
        {p}
      </a>
    ) : (
      <React.Fragment key={i}>{p}</React.Fragment>
    )
  );
}

function prettyTool(name) {
  return String(name || '').replace(/_/g, ' ');
}

function ToolChip({ item }) {
  const [open, setOpen] = useState(false);
  const hasArgs = item.args && Object.keys(item.args).length > 0;
  return (
    <div className={`tool-chip ${item.status}`}>
      <button className="tool-chip-main" onClick={() => setOpen((o) => !o)} title={item.summary || item.name}>
        <span className={`tool-icon ${item.status === 'running' ? 'spin' : ''}`}>{TOOL_ICON[item.status]}</span>
        <span className="tool-name">{prettyTool(item.name)}</span>
        {item.summary && <span className="tool-summary">— {item.summary}</span>}
      </button>
      {open && (hasArgs || item.summary) && (
        <div className="tool-detail">
          {hasArgs && <pre className="code small">{JSON.stringify(item.args, null, 2)}</pre>}
          {item.summary && <div className="small">{item.summary}</div>}
        </div>
      )}
    </div>
  );
}

function Onboarding({ keys, goSettings }) {
  const [hideVoiceTip, setHideVoiceTip] = useState(false);
  if (!keys.groq) {
    return (
      <div className="onboard">
        <h3>Namaste! Main Jarvis hoon.</h3>
        <p>
          To wake me up, add your <b>Groq API key</b> (the brain + speech recognition). Add an <b>ElevenLabs key</b> for a
          premium natural voice — without it I'll use a free voice.
        </p>
        <button className="btn primary" onClick={goSettings}>
          Add API keys
        </button>
      </div>
    );
  }
  if (!keys.elevenlabs && !hideVoiceTip) {
    return (
      <div className="tip">
        <span>Using the free voice. Add an ElevenLabs key in Settings for a more natural one.</span>
        <button className="icon-btn" onClick={() => setHideVoiceTip(true)} title="Dismiss">
          ✕
        </button>
      </div>
    );
  }
  return null;
}

export default function ChatTab({
  items,
  transcript,
  orbState,
  keys,
  settings,
  micMuted,
  onToggleMic,
  onSendText,
  onListen,
  onStop,
  onConfirm,
  onClearChat,
  goSettings,
}) {
  const [text, setText] = useState('');
  const listRef = useRef(null);
  const inputRef = useRef(null);
  const busy = orbState === 'thinking' || orbState === 'speaking' || orbState === 'listening';

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [items, transcript]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const submit = () => {
    if (onSendText(text)) setText('');
  };

  const name = settings?.assistant_name || 'Jarvis';

  return (
    <div className="chat">
      <PermissionsCard compact />
      <Onboarding keys={keys} goSettings={goSettings} />

      <div className="messages" ref={listRef}>
        {items.length === 0 && (
          <div className="empty">
            <p>Say “Hey {name}” or hold the orb to talk.</p>
            <p className="muted small">
              Try: “Safari kholo aur YouTube pe lo-fi chalao” · “Downloads folder saaf karo” · “Notes mein grocery list
              banao”
            </p>
          </div>
        )}
        {items.map((item) => {
          if (item.kind === 'user') {
            return (
              <div key={item.id} className="bubble user">
                {item.text}
              </div>
            );
          }
          if (item.kind === 'assistant') {
            return (
              <div key={item.id} className={`bubble assistant ${item.done ? '' : 'streaming'}`}>
                <Linkified text={item.text} />
                {!item.done && <span className="caret" />}
              </div>
            );
          }
          if (item.kind === 'tool') return <ToolChip key={item.id} item={item} />;
          if (item.kind === 'confirm') {
            return (
              <ConfirmCard
                key={item.id}
                item={item}
                onConfirm={onConfirm}
                voiceHint={settings?.confirm_by_voice !== false}
              />
            );
          }
          return (
            <div key={item.id} className="system-line">
              {item.text}
            </div>
          );
        })}
        {transcript && transcript.text && <div className="bubble user interim">{transcript.text}</div>}
        {orbState === 'listening' && !transcript?.text && <div className="listening-line">Listening…</div>}
        {orbState === 'thinking' && <div className="thinking-line">Thinking<span className="dots" /></div>}
      </div>

      <div className="composer">
        <button
          className={`round-btn mic ${orbState === 'listening' ? 'active' : ''}`}
          title="Talk (⌘⌥Space)"
          onClick={onListen}
        >
          <MicIcon />
        </button>
        <textarea
          ref={inputRef}
          rows={1}
          value={text}
          placeholder={`Message ${name}…`}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        {busy ? (
          <button className="round-btn stop" title="Stop (⌘⌥J)" onClick={onStop}>
            ■
          </button>
        ) : (
          <button className="round-btn send" title="Send" onClick={submit} disabled={!text.trim()}>
            ➤
          </button>
        )}
      </div>

      <div className="chat-footer">
        <label className="switch small">
          <input type="checkbox" checked={!micMuted} onChange={(e) => onToggleMic(!e.target.checked)} />
          <span className="slider" />
          <span>Wake word {micMuted ? 'off' : 'on'}</span>
        </label>
        <button className="link-btn" onClick={onClearChat}>
          Clear chat
        </button>
      </div>
    </div>
  );
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
      <path
        fill="currentColor"
        d="M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z"
      />
    </svg>
  );
}
