// Jarvis — Electron main process.
// One transparent, frameless, always-on-top window. In "orb" mode it is a small
// square holding the orb; in "panel" mode it grows up and to the left (the
// orb's bottom-right corner stays anchored) to show the glass panel.
const path = require('path');
const {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  Notification,
  screen,
  shell,
  dialog,
} = require('electron');
const { EngineManager } = require('./engine');
const { createTray } = require('./tray');
const windowState = require('./windowState');
const permissions = require('./permissions');

const ORB = 140;
const PANEL_W = 440;
const PANEL_H = 760;
const MARGIN = 24;

const DEV_URL = process.env.VITE_DEV_SERVER_URL;

// Allow the orb to speak without a user gesture (audio arrives from the engine).
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');

if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

let win = null;
let trayCtl = null;
let panelOpen = false;
let orbVisible = true;
let micMuted = false;
let quitting = false;
let drag = null;
// Bottom-right corner of the orb, in screen coordinates.
let anchor = null;

const engine = new EngineManager();

function send(channel, payload) {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
}

function startWithSystem() {
  return app.getLoginItemSettings().openAtLogin;
}

function setStartWithSystem(enabled) {
  app.setLoginItemSettings({ openAtLogin: !!enabled, openAsHidden: true });
  refreshTray();
  send('login-item', startWithSystem());
}

function refreshTray() {
  if (trayCtl) {
    trayCtl.rebuild({ orbVisible, micMuted, startWithSystem: startWithSystem() });
  }
}

function defaultAnchor() {
  const { workArea } = screen.getPrimaryDisplay();
  return { x: workArea.x + workArea.width - MARGIN, y: workArea.y + workArea.height - MARGIN };
}

// Keep the anchor on a visible display (monitors can be unplugged between runs).
function clampAnchor(a, w, h) {
  const display = screen.getDisplayNearestPoint({ x: Math.round(a.x), y: Math.round(a.y) });
  const wa = display.workArea;
  return {
    x: Math.min(Math.max(a.x, wa.x + w), wa.x + wa.width),
    y: Math.min(Math.max(a.y, wa.y + h), wa.y + wa.height),
  };
}

function boundsFor(open) {
  const w = open ? PANEL_W : ORB;
  const h = open ? PANEL_H : ORB;
  anchor = clampAnchor(anchor, w, h);
  return { x: Math.round(anchor.x - w), y: Math.round(anchor.y - h), width: w, height: h };
}

function applyBounds() {
  if (!win) return;
  win.setResizable(true);
  win.setBounds(boundsFor(panelOpen));
  win.setResizable(false);
}

function saveState() {
  windowState.save({ anchor });
}

function createWindow() {
  const saved = windowState.load();
  anchor = saved.anchor || defaultAnchor();

  win = new BrowserWindow({
    ...boundsFor(false),
    show: false,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    resizable: false,
    maximizable: false,
    minimizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    focusable: false,
    title: 'Jarvis',
    roundedCorners: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
    },
  });

  win.setAlwaysOnTop(true, 'screen-saver');
  // follow the user across Spaces and over full-screen apps
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true });
  win.setIgnoreMouseEvents(true, { forward: true });

  if (DEV_URL) {
    win.loadURL(DEV_URL);
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  // Show without stealing focus from whatever the user is doing.
  win.once('ready-to-show', () => win.showInactive());

  // Links from the chat open in the real browser, never inside the orb window.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (e, url) => {
    if (DEV_URL && url.startsWith(DEV_URL)) return;
    e.preventDefault();
  });

  win.on('close', (e) => {
    if (!quitting) {
      e.preventDefault();
      setPanel(false);
    }
  });
}

function setPanel(open, tab) {
  if (!win) return;
  panelOpen = !!open;
  if (!orbVisible && panelOpen) setOrbVisible(true);
  applyBounds();
  win.setFocusable(panelOpen);
  if (panelOpen) {
    win.show();
    win.focus();
  }
  send('panel', { open: panelOpen, tab: tab || null });
}

function setOrbVisible(visible) {
  orbVisible = visible;
  if (!win) return;
  if (visible) win.showInactive();
  else {
    panelOpen = false;
    applyBounds();
    win.hide();
  }
  refreshTray();
}

function setMicMuted(muted) {
  micMuted = !!muted;
  send('mic-muted', micMuted);
  refreshTray();
}

// Each action tries its accelerators in order; the first free one wins.
// (Command+Option+Space is Finder search by default on some Macs, hence the fallbacks.)
const SHORTCUTS = {
  talk: {
    keys: ['Command+Option+Space', 'Control+Option+Space', 'Command+Option+K'],
    fn: () => send('shortcut', 'talk'),
  },
  stop: { keys: ['Command+Option+J', 'Control+Option+J'], fn: () => send('shortcut', 'stop') },
  panel: { keys: ['Command+Option+P', 'Control+Option+P'], fn: () => setPanel(!panelOpen) },
  hide: { keys: ['Command+Option+H', 'Control+Option+H'], fn: () => setOrbVisible(!orbVisible) },
};
const activeShortcuts = {};

function registerShortcuts() {
  for (const [action, { keys, fn }] of Object.entries(SHORTCUTS)) {
    activeShortcuts[action] = null;
    for (const accel of keys) {
      try {
        if (globalShortcut.register(accel, fn)) {
          activeShortcuts[action] = accel;
          break;
        }
        console.warn(`[shortcuts] ${accel} is taken by another app`);
      } catch (err) {
        console.warn(`[shortcuts] ${accel}: ${err.message}`);
      }
    }
  }
}

// Renderer warnings/errors go to logs/ui.log so problems are debuggable.
function attachUiLog() {
  const fs = require('fs');
  const file = path.join(app.getPath('userData'), 'logs', 'ui.log');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  win.webContents.on('console-message', (_e, level, message, line, sourceId) => {
    if (level < 2) return; // 2 = warning, 3 = error
    const tag = level === 3 ? 'ERROR' : 'WARN';
    fs.appendFile(file, `${new Date().toISOString()} ${tag} ${message} (${sourceId}:${line})\n`, () => {});
  });
  win.webContents.on('render-process-gone', (_e, details) => {
    fs.appendFile(file, `${new Date().toISOString()} CRASH ${JSON.stringify(details)}\n`, () => {});
  });
}

// Dev-only: JARVIS_SMOKE=1 saves screenshots of the orb and the panel, then quits.
function smokeTest() {
  const fs = require('fs');
  const dir = path.join(app.getPath('userData'), 'smoke');
  fs.mkdirSync(dir, { recursive: true });
  const shot = async (name) => {
    const img = await win.webContents.capturePage();
    fs.writeFileSync(path.join(dir, `${name}.png`), img.toPNG());
  };
  setTimeout(async () => {
    await shot('orb');
    setPanel(true, 'settings');
    setTimeout(async () => {
      await shot('panel-settings');
      send('panel', { open: true, tab: 'chat' });
      setTimeout(async () => {
        await shot('panel-chat');
        // With the mock engine this runs listen → transcript → tool → confirm card.
        send('shortcut', 'talk');
        setTimeout(async () => {
          await shot('panel-confirm');
          quit();
        }, 4000);
      }, 1500);
    }, 1500);
  }, 4000);
}

function setupUpdater() {
  if (!app.isPackaged) return;
  try {
    const { autoUpdater } = require('electron-updater');
    autoUpdater.autoDownload = true;
    autoUpdater.on('error', (err) => console.warn('[updater]', err.message));
    autoUpdater.on('update-downloaded', (info) => {
      new Notification({
        title: 'Jarvis update ready',
        body: `Version ${info.version} will be installed when you quit Jarvis.`,
      }).show();
    });
    autoUpdater.checkForUpdatesAndNotify().catch((err) => console.warn('[updater]', err.message));
  } catch (err) {
    console.warn('[updater] disabled:', err.message);
  }
}

function registerIpc() {
  ipcMain.handle('engine:get', () => engine.info());
  ipcMain.handle('engine:restart', async () => {
    await engine.restart();
    return engine.info();
  });

  ipcMain.handle('win:panel', (_e, open, tab) => {
    setPanel(open, tab);
    return panelOpen;
  });
  ipcMain.on('win:ignore-mouse', (_e, ignore) => {
    if (!win) return;
    if (ignore) win.setIgnoreMouseEvents(true, { forward: true });
    else win.setIgnoreMouseEvents(false);
  });

  ipcMain.on('win:drag-start', () => {
    if (!win) return;
    const cursor = screen.getCursorScreenPoint();
    const [x, y] = win.getPosition();
    drag = { cursor, x, y };
  });
  ipcMain.on('win:drag-move', () => {
    if (!win || !drag) return;
    const c = screen.getCursorScreenPoint();
    const [w, h] = win.getSize();
    const nx = drag.x + (c.x - drag.cursor.x);
    const ny = drag.y + (c.y - drag.cursor.y);
    win.setBounds({ x: nx, y: ny, width: w, height: h });
    anchor = { x: nx + w, y: ny + h };
  });
  ipcMain.on('win:drag-end', () => {
    drag = null;
    applyBounds();
    saveState();
  });

  ipcMain.on('notify', (_e, { title, body }) => {
    if (Notification.isSupported()) {
      new Notification({ title: title || 'Jarvis', body: body || '', silent: false }).show();
    }
  });

  ipcMain.handle('shortcuts:get', () => ({ ...activeShortcuts }));
  ipcMain.handle('login-item:get', () => startWithSystem());
  ipcMain.handle('login-item:set', (_e, enabled) => {
    setStartWithSystem(enabled);
    return startWithSystem();
  });

  ipcMain.on('mic:set-muted', (_e, muted) => {
    micMuted = !!muted;
    refreshTray();
  });

  ipcMain.handle('dialog:pick-folder', async () => {
    const res = await dialog.showOpenDialog(win, {
      title: 'Allow Jarvis to write in this folder',
      properties: ['openDirectory', 'createDirectory'],
    });
    return res.canceled ? null : res.filePaths[0];
  });

  ipcMain.handle('logs:open', () => shell.openPath(path.dirname(engine.logPath())));
  ipcMain.handle('app:quit', () => quit());

  // macOS privacy permissions (Permissions card in the panel)
  ipcMain.handle('permissions:get', () => permissions.status());
  ipcMain.handle('permissions:request', async (_e, id) => {
    const result = await permissions.request(id);
    // Screen Recording / Accessibility take effect for the engine after it restarts.
    return result;
  });
  ipcMain.handle('permissions:open', (_e, id) => shell.openExternal(permissions.PANES[id] || permissions.PANES.microphone));
}

// Re-check permissions whenever the user comes back to Jarvis (e.g. after toggling them in Settings).
let lastPermissions = null;
function watchPermissions() {
  const check = () => {
    const now = JSON.stringify(permissions.status());
    if (now !== lastPermissions) {
      lastPermissions = now;
      send('permissions', JSON.parse(now));
    }
  };
  check();
  setInterval(check, 4000);
}

async function quit() {
  quitting = true;
  await engine.stop();
  app.quit();
}

app.on('second-instance', () => {
  setOrbVisible(true);
  setPanel(true);
});

app.whenReady().then(async () => {
  // Jarvis is a menu-bar + floating-orb app: no Dock icon, no app menu.
  if (app.dock) app.dock.hide();
  registerIpc();
  createWindow();
  attachUiLog();
  watchPermissions();

  // First run: ask for the microphone straight away (the rest are shown in the Permissions card).
  if (permissions.status().find((p) => p.id === 'microphone')?.status === 'not-determined') {
    permissions.request('microphone').catch(() => {});
  }
  if (!permissions.allGranted()) {
    win.once('ready-to-show', () => setTimeout(() => setPanel(true, 'chat'), 800));
  }

  trayCtl = createTray({
    toggleOrb: (forceShow) => setOrbVisible(forceShow ? true : !orbVisible),
    openPanel: (tab) => setPanel(true, tab),
    setMicMuted,
    setStartWithSystem,
    restartEngine: () => engine.restart(),
    openLogs: () => shell.openPath(path.dirname(engine.logPath())),
    quit,
  });
  refreshTray();

  // Keep the orb on screen when monitors change.
  screen.on('display-removed', applyBounds);
  screen.on('display-metrics-changed', applyBounds);

  registerShortcuts();
  engine.on('status', (s) => send('engine:status', engine.info()));
  if (process.env.JARVIS_SMOKE === '1') smokeTest();
  await engine.start();
  setupUpdater();
});

app.on('before-quit', () => {
  quitting = true;
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  engine.stop();
});

// Jarvis lives in the menu bar; closing windows never quits it.
app.on('window-all-closed', () => {});

// Clicking Jarvis in Finder/Launchpad while it's running brings the orb + panel back.
app.on('activate', () => {
  setOrbVisible(true);
  setPanel(true);
});
