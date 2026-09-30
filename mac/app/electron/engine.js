// Spawns and supervises the Python engine (see ../../PROTOCOL.md).
const { spawn } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const net = require('net');
const path = require('path');
const { EventEmitter } = require('events');
const { app } = require('electron');

const READY_TIMEOUT_MS = 60_000;
const MAX_RESTARTS_PER_MINUTE = 5;
const MAX_LOG_BYTES = 5 * 1024 * 1024;

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

function engineDir() {
  return path.resolve(__dirname, '..', '..', 'engine');
}

// Returns { command, args, cwd } or throws with a user-facing message.
function resolveCommand() {
  // Dev aid: JARVIS_MOCK_ENGINE=1 runs a fake engine so the UI works without Python.
  if (!app.isPackaged && process.env.JARVIS_MOCK_ENGINE === '1') {
    const mock = path.resolve(__dirname, '..', 'scripts', 'mock-engine.js');
    return { command: 'node', args: [mock], cwd: path.dirname(mock) };
  }
  if (app.isPackaged) {
    const exe = path.join(process.resourcesPath, 'engine', 'jarvis-engine');
    if (!fs.existsSync(exe)) {
      throw new Error(`Engine binary missing at ${exe}. Reinstall Jarvis.`);
    }
    return { command: exe, args: [], cwd: path.dirname(exe) };
  }
  const dir = engineDir();
  const venvPython = path.join(dir, '.venv', 'bin', 'python3');
  const command = fs.existsSync(venvPython) ? venvPython : 'python3';
  return { command, args: ['-m', 'jarvis'], cwd: dir };
}

// Apps launched from Finder get a minimal PATH; add Homebrew so the engine finds
// `brightness`, `blueutil`, python3 etc.
function enginePath() {
  const extra = ['/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin'];
  const current = (process.env.PATH || '').split(':').filter(Boolean);
  return [...new Set([...extra, ...current])].join(':');
}

class EngineManager extends EventEmitter {
  constructor() {
    super();
    this.proc = null;
    this.port = null;
    this.token = null;
    this.status = { status: 'stopped' };
    this.restartTimes = [];
    this.stopping = false;
    this.readyTimer = null;
    this.tail = [];
    this.logStream = null;
  }

  logPath() {
    return path.join(app.getPath('userData'), 'logs', 'engine.log');
  }

  openLog() {
    const file = this.logPath();
    fs.mkdirSync(path.dirname(file), { recursive: true });
    try {
      if (fs.existsSync(file) && fs.statSync(file).size > MAX_LOG_BYTES) {
        fs.renameSync(file, file + '.old');
      }
    } catch {
      /* log rotation is best-effort */
    }
    this.logStream = fs.createWriteStream(file, { flags: 'a' });
    this.logStream.write(`\n===== engine start ${new Date().toISOString()} =====\n`);
  }

  log(line) {
    this.tail.push(line);
    if (this.tail.length > 30) this.tail.shift();
    if (this.logStream) this.logStream.write(line + '\n');
  }

  setStatus(status) {
    this.status = status;
    this.emit('status', status);
  }

  info() {
    return { ...this.status, port: this.port, token: this.token };
  }

  async start() {
    this.stopping = false;
    this.tail = [];
    let cmd;
    try {
      cmd = resolveCommand();
    } catch (err) {
      this.setStatus({ status: 'error', message: err.message });
      return;
    }

    this.port = await freePort();
    this.token = crypto.randomBytes(24).toString('hex');
    this.setStatus({ status: 'starting' });
    if (!this.logStream) this.openLog();

    const args = [...cmd.args, '--port', String(this.port), '--token', this.token];
    this.log(`$ ${cmd.command} ${cmd.args.join(' ')} --port ${this.port} --token ***`);

    let proc;
    try {
      proc = spawn(cmd.command, args, {
        cwd: cmd.cwd,
        // own process group, so stop() can kill the engine and its children (Playwright, zsh)
        detached: true,
        env: {
          ...process.env,
          PATH: enginePath(),
          JARVIS_DATA_DIR: app.getPath('userData'),
          PYTHONUNBUFFERED: '1',
          PYTHONIOENCODING: 'utf-8',
        },
      });
    } catch (err) {
      this.setStatus({ status: 'error', message: `Could not start engine: ${err.message}` });
      return;
    }
    this.proc = proc;

    let buffer = '';
    proc.stdout.setEncoding('utf8');
    proc.stdout.on('data', (chunk) => {
      buffer += chunk;
      let idx;
      while ((idx = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, idx).replace(/\r$/, '');
        buffer = buffer.slice(idx + 1);
        this.log(line);
        const m = line.match(/^JARVIS_READY\s+(\d+)/);
        if (m && this.status.status !== 'ready') {
          clearTimeout(this.readyTimer);
          this.port = Number(m[1]);
          this.setStatus({ status: 'ready' });
        }
      }
    });
    proc.stderr.setEncoding('utf8');
    proc.stderr.on('data', (chunk) => {
      chunk.split(/\r?\n/).filter(Boolean).forEach((l) => this.log(l));
    });

    proc.on('error', (err) => {
      clearTimeout(this.readyTimer);
      const hint =
        err.code === 'ENOENT'
          ? 'Python was not found. Run ./setup.sh in the mac folder to create the engine venv (see README).'
          : err.message;
      this.log(`[spawn error] ${err.message}`);
      this.proc = null;
      this.setStatus({ status: 'error', message: hint });
    });

    proc.on('exit', (code, signal) => {
      clearTimeout(this.readyTimer);
      this.log(`[engine exited] code=${code} signal=${signal}`);
      if (this.proc !== proc) return;
      this.proc = null;
      if (this.stopping) {
        this.setStatus({ status: 'stopped' });
        return;
      }
      if (this.status.status === 'error') return;
      this.scheduleRestart(code);
    });

    this.readyTimer = setTimeout(() => {
      if (this.status.status === 'starting') {
        this.log('[engine] did not report JARVIS_READY in time');
        this.setStatus({
          status: 'error',
          message: 'The engine did not start in time.\n' + this.tail.slice(-8).join('\n'),
        });
        this.kill();
      }
    }, READY_TIMEOUT_MS);
  }

  scheduleRestart(code) {
    const now = Date.now();
    this.restartTimes = this.restartTimes.filter((t) => now - t < 60_000);
    if (this.restartTimes.length >= MAX_RESTARTS_PER_MINUTE) {
      this.setStatus({
        status: 'error',
        message:
          `The engine keeps crashing (exit code ${code}).\n` + this.tail.slice(-10).join('\n'),
      });
      return;
    }
    this.restartTimes.push(now);
    this.setStatus({ status: 'restarting' });
    setTimeout(() => {
      if (!this.stopping) this.start();
    }, 1000);
  }

  async restart() {
    this.restartTimes = [];
    await this.stop();
    await this.start();
  }

  // Kill the engine's whole process group (it may have children, e.g. Playwright's browser):
  // SIGTERM first, SIGKILL if it's still alive after 2 seconds.
  kill() {
    const proc = this.proc;
    if (!proc || !proc.pid) return;
    const signalGroup = (sig) => {
      try {
        process.kill(-proc.pid, sig);
      } catch {
        try {
          proc.kill(sig);
        } catch {
          /* already gone */
        }
      }
    };
    signalGroup('SIGTERM');
    const force = setTimeout(() => {
      if (proc.exitCode === null && proc.signalCode === null) signalGroup('SIGKILL');
    }, 2000);
    proc.once('exit', () => clearTimeout(force));
  }

  stop() {
    this.stopping = true;
    clearTimeout(this.readyTimer);
    const proc = this.proc;
    if (!proc) return Promise.resolve();
    return new Promise((resolve) => {
      const done = setTimeout(resolve, 3000);
      proc.once('exit', () => {
        clearTimeout(done);
        resolve();
      });
      this.kill();
    });
  }
}

module.exports = { EngineManager };
