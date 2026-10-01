// A fake engine for UI development: speaks PROTOCOL.md over a tiny
// dependency-free WebSocket server. Run the app with JARVIS_MOCK_ENGINE=1.
//   node scripts/mock-engine.js --port 8765 --token dev
const http = require('http');
const crypto = require('crypto');

const args = process.argv.slice(2);
const arg = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : def;
};
const PORT = Number(arg('port', 8765));
const TOKEN = arg('token', 'dev');

let settings = {
  user_name: 'Yogesh',
  assistant_name: 'Jarvis',
  llm_model: 'openai/gpt-oss-120b',
  fast_model: 'openai/gpt-oss-20b',
  vision_model: 'qwen/qwen3.8-27b',
  stt_model: 'whisper-large-v3-turbo',
  tts_provider: 'elevenlabs',
  elevenlabs_voice_id: '',
  elevenlabs_model: 'eleven_flash_v2_5',
  edge_voice: 'hi-IN-MadhurNeural',
  speak_replies: true,
  hindi_script: 'devanagari',
  wake_word_enabled: true,
  wake_word_threshold: 0.5,
  dry_run: false,
  allowed_write_dirs: [],
  confirm_by_voice: true,
  start_with_system: true,
  persona: 'classic',
  address_as: 'sir',
  follow_up: true,
  barge_in: true,
  startup_greeting: true,
  proactive_alerts: true,
  auto_memory: true,
  sound_effects: true,
  home_city: '',
};
const keys = { groq: false, elevenlabs: false };
const audit = [];
const history = [];
const pendingConfirms = new Map();
let hudTimer = null;
let fakeT = 0;
function fakeStats() {
  fakeT += 1;
  const wave = (a, b, p) => a + (b - a) * (0.5 + 0.5 * Math.sin(fakeT / p));
  return {
    ts: Date.now() / 1000,
    cpu: Math.round(wave(12, 58, 3) + Math.random() * 8),
    cpu_ghz: 2.9,
    cores: 12,
    ram: Math.round(wave(52, 61, 9)),
    ram_used_gb: 9.4,
    ram_total_gb: 16,
    disk: 71,
    disk_free_gb: 138,
    battery: { percent: 64, plugged: false, minutes_left: 187 },
    net_up_kbps: Math.round(wave(5, 80, 2)),
    net_down_kbps: Math.round(wave(40, 2400, 4)),
    online: true,
    uptime_s: 5 * 3600 + 1234 + fakeT,
    processes: 284,
    top: [
      { name: 'chrome.exe', cpu: 12.4, mem_mb: 1830 },
      { name: 'Code.exe', cpu: 6.1, mem_mb: 920 },
      { name: 'python.exe', cpu: 3.2, mem_mb: 210 },
      { name: 'explorer.exe', cpu: 1.1, mem_mb: 140 },
      { name: 'Spotify.exe', cpu: 0.8, mem_mb: 310 },
    ],
  };
}

// ---- minimal RFC 6455 (text frames only) ----------------------------------
function encodeFrame(str) {
  const payload = Buffer.from(str, 'utf8');
  let header;
  if (payload.length < 126) {
    header = Buffer.from([0x81, payload.length]);
  } else if (payload.length < 65536) {
    header = Buffer.alloc(4);
    header[0] = 0x81;
    header[1] = 126;
    header.writeUInt16BE(payload.length, 2);
  } else {
    header = Buffer.alloc(10);
    header[0] = 0x81;
    header[1] = 127;
    header.writeBigUInt64BE(BigInt(payload.length), 2);
  }
  return Buffer.concat([header, payload]);
}

function makeParser(onText, onClose) {
  let buf = Buffer.alloc(0);
  return (chunk) => {
    buf = Buffer.concat([buf, chunk]);
    while (buf.length >= 2) {
      const opcode = buf[0] & 0x0f;
      const masked = (buf[1] & 0x80) !== 0;
      let len = buf[1] & 0x7f;
      let off = 2;
      if (len === 126) {
        if (buf.length < 4) return;
        len = buf.readUInt16BE(2);
        off = 4;
      } else if (len === 127) {
        if (buf.length < 10) return;
        len = Number(buf.readBigUInt64BE(2));
        off = 10;
      }
      const maskLen = masked ? 4 : 0;
      if (buf.length < off + maskLen + len) return;
      const mask = masked ? buf.subarray(off, off + 4) : null;
      const data = Buffer.from(buf.subarray(off + maskLen, off + maskLen + len));
      if (mask) for (let i = 0; i < data.length; i++) data[i] ^= mask[i % 4];
      buf = buf.subarray(off + maskLen + len);
      if (opcode === 0x8) return onClose();
      if (opcode === 0x1) onText(data.toString('utf8'));
    }
  };
}

// ---- behaviour -------------------------------------------------------------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let client = null;
let cancelled = false;
const send = (msg) => client && client.write(encodeFrame(JSON.stringify(msg)));
const state = (s) => send({ type: 'state', state: s });

async function streamReply(text) {
  const id = crypto.randomUUID();
  state('thinking');
  await sleep(500);
  for (const word of text.split(/(\s+)/)) {
    if (cancelled) return;
    send({ type: 'assistant_delta', id, text: word });
    await sleep(35);
  }
  send({ type: 'assistant_done', id, text });
  send({ type: 'audio_end', id });
  history.push({ role: 'assistant', text, ts: Date.now() / 1000 });
  state('idle');
}

async function runTool(name, toolArgs, level, summary) {
  const id = crypto.randomUUID();
  send({ type: 'tool_start', id, name, args: toolArgs, level });
  await sleep(700);
  send({ type: 'tool_end', id, ok: true, summary });
  audit.push({ ts: new Date().toISOString(), tool: name, args: toolArgs, level, result: summary, ok: true });
}

async function handleText(text) {
  cancelled = false;
  history.push({ role: 'user', text, ts: Date.now() / 1000 });
  const t = text.toLowerCase();
  if (t.includes('delete') || t.includes('saaf')) {
    const id = crypto.randomUUID();
    state('thinking');
    await runTool('list_directory', { path: 'C:\\Users\\me\\Downloads' }, 'auto', '142 files');
    send({
      type: 'confirm_request',
      id,
      tool: 'organize_folder',
      args: { path: 'C:\\Users\\me\\Downloads', by: 'type' },
      description: 'Move 142 files in Downloads into 6 folders by type.',
    });
    const approved = await new Promise((resolve) => pendingConfirms.set(id, resolve));
    send({ type: 'confirm_resolved', id, approved });
    if (approved) {
      await runTool('organize_folder', { path: 'C:\\Users\\me\\Downloads' }, 'confirm', 'Moved 142 files');
      return streamReply('हो गया! Downloads अब साफ़ है — 142 files, 6 folders में sort कर दीं।');
    }
    return streamReply('ठीक है, कुछ नहीं बदला।');
  }
  if (t.includes('volume')) {
    await runTool('set_volume', { level: 30 }, 'auto', 'Volume 30%');
    return streamReply('Volume 30 पर set कर दिया।');
  }
  if (t.includes('remind')) {
    await streamReply('Done, 10 second में याद दिला दूँगा।');
    setTimeout(() => send({ type: 'notify', title: 'Reminder', body: 'Mom ko call karo', kind: 'reminder' }), 10000);
    return undefined;
  }
  return streamReply(
    `Mock engine here. Aapne kaha: “${text}”. Try "volume", "saaf karo" (confirm flow) or "remind". https://console.groq.com`
  );
}

async function fakeListen() {
  state('listening');
  const words = 'Downloads folder saaf karo'.split(' ');
  let partial = '';
  for (let i = 0; i < 30 && !cancelled; i++) {
    send({ type: 'mic_level', level: 0.2 + Math.random() * 0.7 });
    if (i % 6 === 5 && words.length) {
      partial += (partial ? ' ' : '') + words.shift();
      send({ type: 'transcript', text: partial, final: false });
    }
    await sleep(50);
  }
  if (cancelled) return state('idle');
  const finalText = 'Downloads folder saaf karo';
  send({ type: 'transcript', text: finalText, final: true });
  return handleText(finalText);
}

function onMessage(raw) {
  let msg;
  try {
    msg = JSON.parse(raw);
  } catch {
    return;
  }
  switch (msg.type) {
    case 'text':
      handleText(msg.text);
      break;
    case 'listen':
    case 'ptt_start':
      cancelled = false;
      fakeListen();
      break;
    case 'confirm_response': {
      const resolve = pendingConfirms.get(msg.id);
      pendingConfirms.delete(msg.id);
      if (resolve) resolve(!!msg.approved);
      break;
    }
    case 'stop':
      cancelled = true;
      for (const [id, resolve] of pendingConfirms) {
        send({ type: 'confirm_resolved', id, approved: false });
        resolve(false);
      }
      pendingConfirms.clear();
      state('idle');
      break;
    case 'set_keys':
      if ('groq' in msg) keys.groq = !!msg.groq;
      if ('elevenlabs' in msg) keys.elevenlabs = !!msg.elevenlabs;
      send({ type: 'keys', ...keys });
      break;
    case 'update_settings':
      settings = { ...settings, ...(msg.settings || {}) };
      send({ type: 'settings', settings });
      break;
    case 'get_audit':
      send({ type: 'audit', entries: audit.slice(-(msg.limit || 100)) });
      break;
    case 'get_history':
      send({ type: 'history', messages: history.slice(-(msg.limit || 50)) });
      break;
    case 'clear_history':
      history.length = 0;
      break;
    case 'mic_mute':
      state(msg.muted ? 'sleeping' : 'idle');
      break;
    case 'hud_state':
      clearInterval(hudTimer);
      if (msg.open) {
        send({
          type: 'hud_info',
          weather: { place: 'New Delhi, India', now: '31.2°C (feels 34°C), partly cloudy, humidity 58%, wind 9 km/h' },
          reminders: [
            { text: 'Team standup', due: Date.now() / 1000 + 3600, repeat: 'daily' },
            { text: 'Call Priya — birthday', due: Date.now() / 1000 + 86400, repeat: '' },
          ],
          memories: 14,
          tools: 90,
        });
        const tick = () => send({ type: 'system_stats', stats: fakeStats() });
        tick();
        hudTimer = setInterval(tick, 1500);
      }
      break;
    default:
      break;
  }
}

const server = http.createServer((_req, res) => {
  res.writeHead(426);
  res.end('WebSocket only');
});

server.on('upgrade', (req, socket) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  const key = req.headers['sec-websocket-key'];
  const accept = crypto
    .createHash('sha1')
    .update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11')
    .digest('base64');
  socket.write(
    'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n' +
      `Sec-WebSocket-Accept: ${accept}\r\n\r\n`
  );
  if (url.searchParams.get('token') !== TOKEN) {
    // close frame with code 4401
    const code = Buffer.alloc(2);
    code.writeUInt16BE(4401);
    socket.end(Buffer.concat([Buffer.from([0x88, 2]), code]));
    return;
  }
  client = socket;
  socket.on('data', makeParser(onMessage, () => socket.end()));
  socket.on('error', () => {});
  socket.on('close', () => {
    if (client === socket) client = null;
  });
  send({ type: 'hello', version: '0.1.0-mock', platform: 'windows', keys, settings });
  state('idle');
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`JARVIS_READY ${PORT}`);
});
