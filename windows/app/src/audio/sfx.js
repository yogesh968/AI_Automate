// Tiny synthesized HUD sounds (no audio files): a rising chime when Jarvis starts
// listening, a soft falling blip when it stops, and a short "cut" on interrupt.

let ctx = null;

function audio() {
  if (!ctx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    ctx = new Ctx();
  }
  if (ctx.state === 'suspended') ctx.resume().catch(() => {});
  return ctx;
}

function tone(ac, { freq, to, start = 0, dur = 0.12, gain = 0.06, type = 'sine' }) {
  const t0 = ac.currentTime + start;
  const osc = ac.createOscillator();
  const g = ac.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (to) osc.frequency.exponentialRampToValueAtTime(to, t0 + dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.012);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(g).connect(ac.destination);
  osc.start(t0);
  osc.stop(t0 + dur + 0.02);
}

const SOUNDS = {
  listen: (ac) => {
    tone(ac, { freq: 880, to: 1320, dur: 0.11, gain: 0.05 });
    tone(ac, { freq: 1320, to: 1760, start: 0.09, dur: 0.14, gain: 0.04 });
  },
  done: (ac) => {
    tone(ac, { freq: 1180, to: 760, dur: 0.12, gain: 0.035 });
  },
  interrupt: (ac) => {
    tone(ac, { freq: 520, to: 260, dur: 0.1, gain: 0.05, type: 'triangle' });
  },
  hud: (ac) => {
    tone(ac, { freq: 220, to: 660, dur: 0.35, gain: 0.04, type: 'sawtooth' });
    tone(ac, { freq: 990, to: 1480, start: 0.28, dur: 0.18, gain: 0.03 });
  },
};

export function playSfx(name) {
  try {
    const ac = audio();
    if (ac && SOUNDS[name]) SOUNDS[name](ac);
  } catch (err) {
    console.warn('[sfx]', err);
  }
}
