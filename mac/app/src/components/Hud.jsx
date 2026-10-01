import React, { useEffect, useMemo, useState } from 'react';
import Orb from './Orb.jsx';
import '../hud.css';

// Full-screen Iron Man style heads-up display. Live telemetry comes from the
// engine (`system_stats` every ~1.5 s, `hud_info` for weather/reminders).

const STATE_LABEL = {
  idle: 'STANDING BY',
  listening: 'LISTENING',
  thinking: 'PROCESSING',
  speaking: 'SPEAKING',
  sleeping: 'MIC MUTED',
  error: 'ATTENTION REQUIRED',
  offline: 'CONNECTING',
};

const pad = (n) => String(n).padStart(2, '0');

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function fmtRate(kbps) {
  if (kbps == null) return '—';
  if (kbps >= 1024) return `${(kbps / 1024).toFixed(1)} MB/s`;
  return `${kbps.toFixed(kbps < 10 ? 1 : 0)} KB/s`;
}

function fmtUptime(s) {
  if (!s) return '—';
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return d ? `${d}d ${h}h ${pad(m)}m` : `${h}h ${pad(m)}m`;
}

function fmtDue(due) {
  const d = new Date(due * 1000);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return sameDay ? time : `${d.toLocaleDateString([], { day: 'numeric', month: 'short' })} ${time}`;
}

// Circular gauge. `value` 0..100; turns amber/red past the thresholds.
function Gauge({ label, value, sub, warn = 75, crit = 90, invert = false }) {
  const v = value == null ? 0 : Math.max(0, Math.min(100, value));
  const r = 42;
  const c = 2 * Math.PI * r;
  const bad = invert ? v <= 100 - warn : v >= warn;
  const worse = invert ? v <= 100 - crit : v >= crit;
  const tone = worse ? 'crit' : bad ? 'warn' : 'ok';
  return (
    <div className={`hud-gauge tone-${tone}`}>
      <svg viewBox="0 0 100 100">
        <circle className="g-track" cx="50" cy="50" r={r} />
        <circle
          className="g-ticks"
          cx="50"
          cy="50"
          r={r + 6}
          strokeDasharray={`1 ${((2 * Math.PI * (r + 6)) / 60 - 1).toFixed(3)}`}
        />
        <circle
          className="g-value"
          cx="50"
          cy="50"
          r={r}
          strokeDasharray={`${(c * v) / 100} ${c}`}
          transform="rotate(-90 50 50)"
        />
      </svg>
      <div className="g-center">
        <div className="g-num">{value == null ? '—' : Math.round(v)}<span>%</span></div>
        <div className="g-label">{label}</div>
      </div>
      {sub && <div className="g-sub">{sub}</div>}
    </div>
  );
}

function Spark({ data, max, className = '' }) {
  const w = 240;
  const h = 46;
  if (!data.length) return <svg className={`hud-spark ${className}`} viewBox={`0 0 ${w} ${h}`} />;
  const top = max || Math.max(1, ...data);
  const step = w / Math.max(1, data.length - 1);
  const pts = data.map((v, i) => `${(i * step).toFixed(1)},${(h - (v / top) * (h - 4) - 2).toFixed(1)}`);
  return (
    <svg className={`hud-spark ${className}`} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <polygon points={`0,${h} ${pts.join(' ')} ${w},${h}`} className="s-fill" />
      <polyline points={pts.join(' ')} className="s-line" />
    </svg>
  );
}

function Card({ title, children, className = '' }) {
  return (
    <section className={`hud-card ${className}`}>
      <header>
        <span className="hud-card-mark" />
        {title}
      </header>
      {children}
    </section>
  );
}

export default function Hud({ state, getLevel, stats, history, info, items, transcript, settings, onClose, onTalk }) {
  const now = useClock();
  const s = stats || {};
  const userName = settings?.user_name || '';
  const hour = now.getHours();
  const pod = hour < 5 ? 'night' : hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : hour < 22 ? 'evening' : 'night';

  const lastReply = useMemo(() => {
    for (let i = items.length - 1; i >= 0; i--) if (items[i].kind === 'assistant' && items[i].text) return items[i];
    return null;
  }, [items]);
  const lastUser = useMemo(() => {
    for (let i = items.length - 1; i >= 0; i--) if (items[i].kind === 'user') return items[i];
    return null;
  }, [items]);
  const actions = useMemo(() => items.filter((i) => i.kind === 'tool').slice(-6).reverse(), [items]);

  const bat = s.battery;
  const weather = info?.weather;

  return (
    <div className="hud" data-hit>
      <div className="hud-grid" aria-hidden />
      <div className="hud-scan" aria-hidden />
      <div className="hud-vignette" aria-hidden />

      {/* ---------------- top bar */}
      <header className="hud-top">
        <div className="hud-brand">
          <div className="hud-title">J.A.R.V.I.S.</div>
          <div className="hud-subtitle">Just A Rather Very Intelligent System</div>
        </div>
        <div className="hud-clock">
          <div className="hud-time">
            {pad(now.getHours())}:{pad(now.getMinutes())}
            <span className="hud-sec">{pad(now.getSeconds())}</span>
          </div>
          <div className="hud-date">
            {now.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </div>
        </div>
        <div className="hud-weather">
          {weather ? (
            <>
              <div className="hud-temp">{String(weather.now || '').split(' ')[0]}</div>
              <div className="hud-wx">{String(weather.now || '').split(', ').slice(1, 2).join('') || '—'}</div>
              <div className="hud-place">{weather.place}</div>
            </>
          ) : (
            <div className="hud-wx muted">Weather unavailable</div>
          )}
        </div>
      </header>

      {/* ---------------- left: vitals */}
      <aside className="hud-left">
        <Card title="SYSTEM VITALS">
          <div className="hud-gauges">
            <Gauge label="CPU" value={s.cpu} sub={s.cpu_ghz ? `${s.cpu_ghz} GHz · ${s.cores} cores` : null} />
            <Gauge label="MEMORY" value={s.ram} sub={s.ram_total_gb ? `${s.ram_used_gb} / ${s.ram_total_gb} GB` : null} />
            <Gauge label="DISK" value={s.disk} sub={s.disk_free_gb != null ? `${s.disk_free_gb} GB free` : null} warn={85} crit={95} />
            {bat ? (
              <Gauge
                label={bat.plugged ? 'CHARGING' : 'BATTERY'}
                value={bat.percent}
                invert
                warn={80}
                crit={90}
                sub={bat.minutes_left ? `${Math.floor(bat.minutes_left / 60)}h ${pad(bat.minutes_left % 60)}m left` : bat.plugged ? 'on AC power' : null}
              />
            ) : (
              <Gauge label="POWER" value={100} sub="AC power" />
            )}
          </div>
        </Card>
        <Card title="CPU LOAD — 90 s">
          <Spark data={history.cpu} max={100} />
        </Card>
        <Card title="MEMORY — 90 s">
          <Spark data={history.ram} max={100} className="violet" />
        </Card>
      </aside>

      {/* ---------------- center: the core */}
      <main className="hud-center">
        <div className="hud-core">
          <div className="hud-ring r1" />
          <div className="hud-ring r2" />
          <div className="hud-ring r3" />
          <div className="hud-ring r4" />
          <div className="hud-orb" onClick={onTalk} title="Click to talk">
            <Orb state={state} getLevel={getLevel} />
          </div>
        </div>
        <div className={`hud-state st-${state}`}>{STATE_LABEL[state] || state}</div>
        <div className="hud-subs">
          {transcript?.text ? (
            <p className="hud-you">“{transcript.text}”</p>
          ) : lastUser ? (
            <p className="hud-you">“{lastUser.text}”</p>
          ) : (
            <p className="hud-you muted">
              Good {pod}{userName ? `, ${userName}` : ''}. Say “Hey Jarvis” or click the core.
            </p>
          )}
          {lastReply && <p className="hud-reply">{lastReply.text}</p>}
        </div>
      </main>

      {/* ---------------- right: network, processes, reminders */}
      <aside className="hud-right">
        <Card title="NETWORK">
          <div className="hud-kv">
            <span>Status</span>
            <b className={s.online === false ? 'bad' : 'good'}>{s.online === false ? 'OFFLINE' : 'ONLINE'}</b>
          </div>
          <div className="hud-kv">
            <span>↓ Down</span>
            <b>{fmtRate(s.net_down_kbps)}</b>
          </div>
          <div className="hud-kv">
            <span>↑ Up</span>
            <b>{fmtRate(s.net_up_kbps)}</b>
          </div>
          <Spark data={history.down} />
        </Card>
        <Card title="TOP PROCESSES">
          {(s.top || []).length === 0 && <p className="muted small">Scanning…</p>}
          {(s.top || []).map((p) => (
            <div className="hud-proc" key={p.name + p.mem_mb}>
              <span className="p-name">{p.name.replace(/\.exe$/i, '')}</span>
              <span className="p-bar">
                <i style={{ width: `${Math.min(100, p.cpu * 2)}%` }} />
              </span>
              <span className="p-num">{p.cpu.toFixed(1)}%</span>
              <span className="p-mem">{p.mem_mb >= 1024 ? `${(p.mem_mb / 1024).toFixed(1)}G` : `${p.mem_mb}M`}</span>
            </div>
          ))}
        </Card>
        <Card title="SCHEDULE">
          {(info?.reminders || []).length === 0 ? (
            <p className="muted small">No pending reminders.</p>
          ) : (
            info.reminders.map((r, i) => (
              <div className="hud-rem" key={i}>
                <span className="r-time">{fmtDue(r.due)}</span>
                <span className="r-text">{r.text}</span>
              </div>
            ))
          )}
        </Card>
        <Card title="CORE">
          <div className="hud-kv">
            <span>Uptime</span>
            <b>{fmtUptime(s.uptime_s)}</b>
          </div>
          <div className="hud-kv">
            <span>Processes</span>
            <b>{s.processes ?? '—'}</b>
          </div>
          <div className="hud-kv">
            <span>Protocols loaded</span>
            <b>{info?.tools ?? '—'}</b>
          </div>
          <div className="hud-kv">
            <span>Memories</span>
            <b>{info?.memories ?? '—'}</b>
          </div>
        </Card>
      </aside>

      {/* ---------------- bottom: action log */}
      <footer className="hud-bottom">
        <div className="hud-log">
          {actions.length === 0 ? (
            <span className="muted">No actions yet this session.</span>
          ) : (
            actions.map((a) => (
              <span key={a.id} className={`hud-log-item s-${a.status}`}>
                {a.status === 'running' ? '◌' : a.status === 'ok' ? '✓' : '✕'} {a.name.replace(/_/g, ' ')}
              </span>
            ))
          )}
        </div>
        <div className="hud-help">
          <kbd>Esc</kbd> exit HUD
          <button className="hud-exit" onClick={onClose}>
            CLOSE
          </button>
        </div>
      </footer>
    </div>
  );
}
