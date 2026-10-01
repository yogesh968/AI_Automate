// Safe bridge between the renderer and the main process.
const { contextBridge, ipcRenderer } = require('electron');

function subscribe(channel, cb) {
  const handler = (_e, payload) => cb(payload);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
}

contextBridge.exposeInMainWorld('jarvis', {
  platform: 'macos',

  // Engine process
  getEngine: () => ipcRenderer.invoke('engine:get'),
  restartEngine: () => ipcRenderer.invoke('engine:restart'),
  onEngineStatus: (cb) => subscribe('engine:status', cb),

  // Window
  setPanel: (open, tab) => ipcRenderer.invoke('win:panel', open, tab),
  onPanel: (cb) => subscribe('panel', cb),
  setHud: (open) => ipcRenderer.invoke('win:hud', !!open),
  setIgnoreMouse: (ignore) => ipcRenderer.send('win:ignore-mouse', !!ignore),
  dragStart: () => ipcRenderer.send('win:drag-start'),
  dragMove: () => ipcRenderer.send('win:drag-move'),
  dragEnd: () => ipcRenderer.send('win:drag-end'),

  // Shortcuts + tray
  onShortcut: (cb) => subscribe('shortcut', cb),
  onMicMuted: (cb) => subscribe('mic-muted', cb),
  setMicMuted: (muted) => ipcRenderer.send('mic:set-muted', !!muted),

  // System
  getShortcuts: () => ipcRenderer.invoke('shortcuts:get'),
  notify: (title, body) => ipcRenderer.send('notify', { title, body }),
  getLoginItem: () => ipcRenderer.invoke('login-item:get'),
  setLoginItem: (enabled) => ipcRenderer.invoke('login-item:set', !!enabled),
  onLoginItem: (cb) => subscribe('login-item', cb),
  pickFolder: () => ipcRenderer.invoke('dialog:pick-folder'),
  openLogs: () => ipcRenderer.invoke('logs:open'),
  quit: () => ipcRenderer.invoke('app:quit'),

  // macOS privacy permissions
  getPermissions: () => ipcRenderer.invoke('permissions:get'),
  requestPermission: (id) => ipcRenderer.invoke('permissions:request', id),
  openPermissionPane: (id) => ipcRenderer.invoke('permissions:open', id),
  onPermissions: (cb) => subscribe('permissions', cb),
});
