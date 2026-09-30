// Plays the engine's spoken replies in order and exposes a live amplitude
// (0..1) so the orb can pulse with Jarvis's voice.
//
// Each reply has an `id`; sentences arrive as `audio` messages with a `seq`.
// Replies play in arrival order, sentences in seq order. `stop()` clears
// everything immediately (kill switch).

function b64ToArrayBuffer(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

export class AudioPlayer {
  constructor({ onPlayingChange } = {}) {
    this.onPlayingChange = onPlayingChange || (() => {});
    this.ctx = null;
    this.analyser = null;
    this.gain = null;
    this.data = null;
    this.replies = []; // [{ id, next, chunks: Map<seq, Promise<AudioBuffer>>, ended }]
    this.current = null; // AudioBufferSourceNode
    this.playing = false;
    this.pumping = false;
    this.generation = 0;
    this.idleTimer = null;
  }

  ensureContext() {
    if (this.ctx) return;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    this.ctx = new Ctx();
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 1024;
    this.analyser.smoothingTimeConstant = 0.6;
    this.gain = this.ctx.createGain();
    this.gain.connect(this.analyser);
    this.analyser.connect(this.ctx.destination);
    this.data = new Uint8Array(this.analyser.fftSize);
  }

  reply(id) {
    let r = this.replies.find((x) => x.id === id);
    if (!r) {
      r = { id, next: 0, chunks: new Map(), ended: false };
      this.replies.push(r);
    }
    return r;
  }

  enqueue(msg) {
    this.ensureContext();
    if (this.ctx.state === 'suspended') this.ctx.resume().catch(() => {});
    const r = this.reply(msg.id);
    const gen = this.generation;
    const decoded = this.ctx
      .decodeAudioData(b64ToArrayBuffer(msg.data))
      .catch((err) => {
        console.warn('[audio] decode failed', err);
        return null;
      });
    r.chunks.set(Number(msg.seq) || 0, decoded);
    // Sentence numbering may start at 0 or 1; begin at the lowest seen.
    if (r.next === 0 && !r.chunks.has(0)) r.next = Math.min(...r.chunks.keys());
    if (gen === this.generation) this.pump();
  }

  end(id) {
    this.reply(id).ended = true;
    this.pump();
  }

  setPlaying(p) {
    clearTimeout(this.idleTimer);
    if (p) {
      if (!this.playing) {
        this.playing = true;
        this.onPlayingChange(true);
      }
    } else if (this.playing) {
      // Short grace period so the gap between sentences doesn't flicker.
      this.idleTimer = setTimeout(() => {
        this.playing = false;
        this.onPlayingChange(false);
      }, 350);
    }
  }

  async pump() {
    if (this.pumping) return;
    this.pumping = true;
    const gen = this.generation;
    try {
      while (gen === this.generation && this.replies.length) {
        const r = this.replies[0];
        if (!r.chunks.has(r.next)) {
          if (r.ended && r.chunks.size === 0) {
            this.replies.shift();
            continue;
          }
          if (r.ended) {
            // Missing sequence number — skip ahead to the next available one.
            r.next = Math.min(...r.chunks.keys());
            continue;
          }
          break; // wait for more audio
        }
        const promise = r.chunks.get(r.next);
        r.chunks.delete(r.next);
        r.next += 1;
        const buffer = await promise;
        if (gen !== this.generation) return;
        if (buffer) await this.playBuffer(buffer, gen);
      }
    } finally {
      if (gen === this.generation) this.pumping = false;
    }
    if (gen === this.generation && !this.current) this.setPlaying(false);
  }

  playBuffer(buffer, gen) {
    return new Promise((resolve) => {
      if (gen !== this.generation) return resolve();
      const src = this.ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(this.gain);
      this.current = src;
      this.setPlaying(true);
      src.onended = () => {
        if (this.current === src) this.current = null;
        resolve();
      };
      src.start();
    });
  }

  stop() {
    this.generation += 1;
    this.pumping = false;
    this.replies = [];
    if (this.current) {
      try {
        this.current.onended = null;
        this.current.stop();
      } catch {
        /* already stopped */
      }
      this.current = null;
    }
    clearTimeout(this.idleTimer);
    if (this.playing) {
      this.playing = false;
      this.onPlayingChange(false);
    }
  }

  // Current loudness 0..1 of what's playing.
  level() {
    if (!this.analyser || !this.current) return 0;
    this.analyser.getByteTimeDomainData(this.data);
    let sum = 0;
    for (let i = 0; i < this.data.length; i++) {
      const v = (this.data[i] - 128) / 128;
      sum += v * v;
    }
    return Math.min(1, Math.sqrt(sum / this.data.length) * 3.2);
  }
}
