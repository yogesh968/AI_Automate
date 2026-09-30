import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { bridge } from './bridge.js';
import { useEngine } from './hooks/useEngine.js';
import { AudioPlayer } from './audio/player.js';
import Orb from './components/Orb.jsx';
import Panel from './components/Panel.jsx';
import Toasts from './components/Toasts.jsx';

let localId = 0;
const nextLocalId = (p) => `${p}-${Date.now()}-${++localId}`;

// ---- chat timeline ---------------------------------------------------------
// Items: user | assistant | tool | confirm | system
function chatReducer(items, action) {
  switch (action.type) {
    case 'reset':
      return action.items || [];
    case 'user':
      return [...items, { kind: 'user', id: nextLocalId('u'), text: action.text, ts: Date.now() }];
    case 'system':
      return [...items, { kind: 'system', id: nextLocalId('s'), text: action.text, ts: Date.now() }];
    case 'delta': {
      const idx = items.findIndex((i) => i.kind === 'assistant' && i.id === action.id);
      if (idx < 0) {
        return [...items, { kind: 'assistant', id: action.id, text: action.text, done: false, ts: Date.now() }];
      }
      const copy = items.slice();
      copy[idx] = { ...copy[idx], text: copy[idx].text + action.text };
      return copy;
    }
    case 'done': {
      const idx = items.findIndex((i) => i.kind === 'assistant' && i.id === action.id);
      if (idx < 0) {
        if (!action.text) return items;
        return [...items, { kind: 'assistant', id: action.id, text: action.text, done: true, ts: Date.now() }];
      }
      const copy = items.slice();
      copy[idx] = { ...copy[idx], text: action.text || copy[idx].text, done: true };
      return copy;
    }
    case 'tool_start':
      return [
        ...items,
        {
          kind: 'tool',
          id: action.id,
          name: action.name,
          args: action.args || {},
          level: action.level || 'auto',
          status: 'running',
          summary: '',
          ts: Date.now(),
        },
      ];
    case 'tool_end':
      return items.map((i) =>
        i.kind === 'tool' && i.id === action.id
          ? { ...i, status: action.ok ? 'ok' : 'failed', summary: action.summary || '' }
          : i
      );
    case 'confirm_request':
      return [
        ...items,
        {
          kind: 'confirm',
          id: action.id,
          tool: action.tool,
          args: action.args || {},
          description: action.description || '',
          status: 'pending',
          ts: Date.now(),
        },
      ];
    case 'confirm_resolved':
      return items.map((i) =>
        i.kind === 'confirm' && i.id === action.id
          ? { ...i, status: action.approved ? 'approved' : 'denied' }
          : i
      );
    case 'cancel_running':
      return items.map((i) => {
        if (i.kind === 'tool' && i.status === 'running') return { ...i, status: 'failed', summary: 'Stopped' };
        if (i.kind === 'confirm' && i.status === 'pending') return { ...i, status: 'denied' };
        if (i.kind === 'assistant' && !i.done) return { ...i, done: true };
        return i;
      });
    default:
      return items;
  }
}

export default function App() {
  const [items, dispatch] = useReducer(chatReducer, []);
  const [orbState, setOrbState] = useState('idle');
  const [transcript, setTranscript] = useState(null);
  const [hello, setHello] = useState(null);
  const [keys, setKeys] = useState({ groq: false, elevenlabs: false });
  const [settings, setSettings] = useState(null);
  const [audit, setAudit] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [panelOpen, setPanelOpen] = useState(false);
  const [tab, setTab] = useState('chat');
  const [micMuted, setMicMuted] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  const micLevel = useRef({ value: 0, t: 0 });
  const panelOpenRef = useRef(false);
  panelOpenRef.current = panelOpen;
  const micMutedRef = useRef(false);
  micMutedRef.current = micMuted;
  const sendRef = useRef(() => false);
  const openedForErrorRef = useRef(false);

  const toast = useCallback((title, body, kind = 'info') => {
    const id = nextLocalId('t');
    setToasts((t) => [...t.slice(-3), { id, title, body, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'reminder' ? 12000 : 6000);
  }, []);
  const dismissToast = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  // Audio player lives for the whole session.
  const playerRef = useRef(null);
  if (!playerRef.current) {
    playerRef.current = new AudioPlayer({
      onPlayingChange: (playing) => {
        setSpeaking(playing);
        sendRef.current({ type: 'audio_state', playing });
      },
    });
  }
  const player = playerRef.current;

  const openPanel = useCallback((open, nextTab) => {
    if (nextTab) setTab(nextTab);
    bridge.setPanel(open, nextTab);
    setPanelOpen(open);
  }, []);

  // ---- engine messages ----------------------------------------------------
  const onMessage = useCallback(
    (msg) => {
      switch (msg.type) {
        case 'hello':
          setHello(msg);
          if (msg.keys) setKeys(msg.keys);
          if (msg.settings) setSettings(msg.settings);
          sendRef.current({ type: 'get_history', limit: 60 });
          sendRef.current({ type: 'mic_mute', muted: micMutedRef.current });
          break;
        case 'state':
          setOrbState(msg.state);
          if (msg.state !== 'listening') setTranscript((t) => (t && !t.final ? null : t));
          break;
        case 'mic_level':
          micLevel.current = { value: Number(msg.level) || 0, t: performance.now() };
          break;
        case 'transcript':
          if (msg.final) {
            setTranscript(null);
            if (msg.text && msg.text.trim()) dispatch({ type: 'user', text: msg.text.trim() });
          } else {
            setTranscript({ text: msg.text, final: false });
          }
          break;
        case 'assistant_delta':
          dispatch({ type: 'delta', id: msg.id, text: msg.text || '' });
          break;
        case 'assistant_done':
          dispatch({ type: 'done', id: msg.id, text: msg.text || '' });
          break;
        case 'tool_start':
          dispatch({ type: 'tool_start', id: msg.id, name: msg.name, args: msg.args, level: msg.level });
          break;
        case 'tool_end':
          dispatch({ type: 'tool_end', id: msg.id, ok: msg.ok, summary: msg.summary });
          break;
        case 'confirm_request':
          dispatch({
            type: 'confirm_request',
            id: msg.id,
            tool: msg.tool,
            args: msg.args,
            description: msg.description,
          });
          // Approval needs the user's eyes — bring the panel up.
          if (!panelOpenRef.current) openPanel(true, 'chat');
          else setTab('chat');
          break;
        case 'confirm_resolved':
          dispatch({ type: 'confirm_resolved', id: msg.id, approved: msg.approved });
          break;
        case 'audio':
          if (msg.data) player.enqueue(msg);
          break;
        case 'audio_end':
          player.end(msg.id);
          break;
        case 'notify':
          toast(msg.title || 'Jarvis', msg.body || '', msg.kind || 'info');
          if (!panelOpenRef.current || msg.kind === 'reminder') bridge.notify(msg.title || 'Jarvis', msg.body || '');
          break;
        case 'settings':
          if (msg.settings) setSettings(msg.settings);
          break;
        case 'keys':
          setKeys({ groq: !!msg.groq, elevenlabs: !!msg.elevenlabs });
          break;
        case 'audit':
          setAudit(Array.isArray(msg.entries) ? msg.entries : []);
          break;
        case 'history':
          if (Array.isArray(msg.messages)) {
            dispatch({
              type: 'reset',
              items: msg.messages
                .filter((m) => m.role === 'user' || m.role === 'assistant')
                .map((m, i) => ({
                  kind: m.role,
                  id: `h-${i}-${m.ts || 0}`,
                  text: m.text || '',
                  done: true,
                  ts: m.ts ? m.ts * (m.ts < 1e12 ? 1000 : 1) : Date.now(),
                })),
            });
          }
          break;
        case 'error':
          toast('Something went wrong', msg.message || 'Unknown error', 'error');
          break;
        default:
          break;
      }
    },
    [openPanel, player, toast]
  );

  const { engine, conn, send, restart } = useEngine(onMessage);
  sendRef.current = send;

  // Surface engine startup failures instead of leaving a silent orb.
  useEffect(() => {
    if (engine.status === 'error' && !openedForErrorRef.current) {
      openedForErrorRef.current = true;
      openPanel(true, 'chat');
    }
    if (engine.status === 'ready') openedForErrorRef.current = false;
  }, [engine.status, openPanel]);

  // ---- actions ------------------------------------------------------------
  const requireConn = useCallback(() => {
    if (conn === 'open') return true;
    toast('Jarvis is offline', 'The engine is not connected yet.', 'warning');
    return false;
  }, [conn, toast]);

  const sendText = useCallback(
    (text) => {
      const t = text.trim();
      if (!t || !requireConn()) return false;
      player.stop();
      dispatch({ type: 'user', text: t });
      send({ type: 'text', text: t });
      return true;
    },
    [player, requireConn, send]
  );

  const listen = useCallback(() => {
    if (!requireConn()) return;
    player.stop();
    send({ type: 'listen' });
  }, [player, requireConn, send]);

  const pttStart = useCallback(() => {
    if (!requireConn()) return;
    player.stop();
    send({ type: 'ptt_start' });
  }, [player, requireConn, send]);

  const pttStop = useCallback(() => send({ type: 'ptt_stop' }), [send]);

  const stop = useCallback(() => {
    player.stop();
    send({ type: 'stop' });
    dispatch({ type: 'cancel_running' });
    setTranscript(null);
  }, [player, send]);

  const confirm = useCallback(
    (id, approved) => {
      send({ type: 'confirm_response', id, approved });
      dispatch({ type: 'confirm_resolved', id, approved });
    },
    [send]
  );

  const toggleMic = useCallback(
    (muted) => {
      setMicMuted(muted);
      bridge.setMicMuted(muted);
      send({ type: 'mic_mute', muted });
    },
    [send]
  );

  // ---- main-process events ------------------------------------------------
  useEffect(() => {
    const offPanel = bridge.onPanel(({ open, tab: t }) => {
      setPanelOpen(open);
      if (t) setTab(t);
    });
    const offMute = bridge.onMicMuted((muted) => {
      setMicMuted(muted);
      sendRef.current({ type: 'mic_mute', muted });
    });
    return () => {
      offPanel();
      offMute();
    };
  }, []);

  const shortcutRef = useRef({});
  shortcutRef.current = { listen, stop };
  useEffect(
    () =>
      bridge.onShortcut((name) => {
        if (name === 'talk') shortcutRef.current.listen();
        if (name === 'stop') shortcutRef.current.stop();
      }),
    []
  );

  // Click-through: only the orb and the panel catch the mouse.
  useEffect(() => {
    let ignoring = true;
    const onMove = (e) => {
      const hit = !!(e.target && e.target.closest && e.target.closest('[data-hit]'));
      if (hit === !ignoring) return;
      ignoring = !hit;
      bridge.setIgnoreMouse(ignoring);
    };
    const onLeave = () => {
      if (!ignoring) {
        ignoring = true;
        bridge.setIgnoreMouse(true);
      }
    };
    window.addEventListener('mousemove', onMove);
    document.addEventListener('mouseleave', onLeave);
    return () => {
      window.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseleave', onLeave);
    };
  }, []);

  // Esc closes the panel.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape' && panelOpenRef.current) openPanel(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [openPanel]);

  // ---- orb ----------------------------------------------------------------
  let visualState = orbState;
  if (engine.status === 'error') visualState = 'error';
  else if (conn !== 'open') visualState = 'offline';
  else if (speaking && orbState !== 'listening') visualState = 'speaking';
  else if (micMuted && orbState === 'idle') visualState = 'sleeping';

  const getLevel = useCallback(() => {
    if (player.playing) return player.level();
    const m = micLevel.current;
    const age = performance.now() - m.t;
    return age > 250 ? 0 : m.value;
  }, [player]);

  return (
    <div className={`app ${panelOpen ? 'panel-open' : ''}`}>
      {panelOpen && (
        <Panel
          tab={tab}
          setTab={setTab}
          onClose={() => openPanel(false)}
          engine={engine}
          conn={conn}
          restartEngine={restart}
          orbState={visualState}
          hello={hello}
          keys={keys}
          settings={settings}
          items={items}
          transcript={transcript}
          audit={audit}
          micMuted={micMuted}
          onToggleMic={toggleMic}
          onSendText={sendText}
          onListen={listen}
          onStop={stop}
          onConfirm={confirm}
          send={send}
          toast={toast}
          onClearChat={() => {
            send({ type: 'clear_history' });
            dispatch({ type: 'reset', items: [] });
          }}
        />
      )}
      <OrbHandle
        state={visualState}
        getLevel={getLevel}
        panelOpen={panelOpen}
        onClick={() => openPanel(!panelOpenRef.current, panelOpenRef.current ? undefined : 'chat')}
        onTalk={listen}
        onPttStart={pttStart}
        onPttStop={pttStop}
      />
      {/* With the panel closed the window is only orb-sized; system notifications cover that case. */}
      {panelOpen && <Toasts toasts={toasts} onDismiss={dismissToast} />}
    </div>
  );
}

// ---- orb interactions ------------------------------------------------------
// click = toggle panel · drag = move · hold = push-to-talk · right-click = talk
function OrbHandle({ state, getLevel, panelOpen, onClick, onTalk, onPttStart, onPttStop }) {
  const g = useRef(null);

  const onPointerDown = (e) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    bridge.dragStart();
    const gesture = { x: e.screenX, y: e.screenY, dragging: false, ptt: false, timer: null };
    gesture.timer = setTimeout(() => {
      if (!gesture.dragging) {
        gesture.ptt = true;
        onPttStart();
      }
    }, 450);
    g.current = gesture;
  };

  const onPointerMove = (e) => {
    const gesture = g.current;
    if (!gesture) return;
    if (!gesture.dragging && !gesture.ptt && Math.hypot(e.screenX - gesture.x, e.screenY - gesture.y) > 4) {
      gesture.dragging = true;
      clearTimeout(gesture.timer);
    }
    if (gesture.dragging) bridge.dragMove();
  };

  const onPointerUp = (e) => {
    const gesture = g.current;
    g.current = null;
    if (!gesture) return;
    clearTimeout(gesture.timer);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* not captured */
    }
    bridge.dragEnd();
    if (gesture.ptt) onPttStop();
    else if (!gesture.dragging) onClick();
  };

  const labels = {
    idle: 'Online',
    listening: 'Listening…',
    thinking: 'Thinking…',
    speaking: 'Speaking',
    sleeping: 'Mic muted',
    error: 'Needs attention',
    offline: 'Connecting…',
  };

  return (
    <div
      className={`orb-wrap ${panelOpen ? 'with-panel' : ''}`}
      data-hit
      title={`Jarvis — ${labels[state] || state}\nClick: panel · Hold: talk · Right-click: talk · Drag: move`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onContextMenu={(e) => {
        e.preventDefault();
        onTalk();
      }}
    >
      <Orb state={state} getLevel={getLevel} />
      <div className={`orb-status orb-status-${state}`}>{labels[state] || state}</div>
    </div>
  );
}
