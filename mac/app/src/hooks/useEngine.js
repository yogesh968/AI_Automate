import { useCallback, useEffect, useRef, useState } from 'react';
import { bridge } from '../bridge.js';

// Connects to the Python engine's WebSocket (see PROTOCOL.md) and keeps
// reconnecting while the engine process is alive.
//   engine: { status, message, port, token } from the main process
//   conn:   'connecting' | 'open' | 'closed'
export function useEngine(onMessage) {
  const [engine, setEngine] = useState({ status: 'starting' });
  const [conn, setConn] = useState('connecting');
  const wsRef = useRef(null);
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;

  // Engine process status from the main process.
  useEffect(() => {
    let alive = true;
    bridge.getEngine().then((info) => alive && setEngine(info));
    const off = bridge.onEngineStatus((info) => setEngine(info));
    return () => {
      alive = false;
      off();
    };
  }, []);

  // WebSocket lifecycle, keyed on the engine's port + token.
  useEffect(() => {
    if (engine.status !== 'ready' || !engine.port || !engine.token) {
      setConn('closed');
      return undefined;
    }
    let closedByUs = false;
    let retryTimer = null;
    let attempt = 0;

    const connect = () => {
      setConn('connecting');
      const ws = new WebSocket(`ws://127.0.0.1:${engine.port}/?token=${engine.token}`);
      wsRef.current = ws;
      ws.onopen = () => {
        attempt = 0;
        setConn('open');
      };
      ws.onmessage = (ev) => {
        let msg;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (msg && typeof msg.type === 'string') handlerRef.current?.(msg);
      };
      ws.onclose = (ev) => {
        if (wsRef.current === ws) wsRef.current = null;
        setConn('closed');
        if (closedByUs) return;
        if (ev.code === 4401) {
          setEngine((e) => ({ ...e, status: 'error', message: 'Engine rejected the session token.' }));
          return;
        }
        attempt += 1;
        const delay = Math.min(5000, 400 * 2 ** Math.min(attempt, 4));
        retryTimer = setTimeout(connect, delay);
      };
      ws.onerror = () => {
        /* onclose follows and handles the retry */
      };
    };

    connect();
    return () => {
      closedByUs = true;
      clearTimeout(retryTimer);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [engine.status, engine.port, engine.token]);

  const send = useCallback((msg) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
      return true;
    }
    return false;
  }, []);

  const restart = useCallback(async () => {
    setEngine({ status: 'starting' });
    const info = await bridge.restartEngine();
    setEngine(info);
  }, []);

  return { engine, conn, send, restart };
}
