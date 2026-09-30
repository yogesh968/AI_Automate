// The preload bridge. When the renderer is opened in a normal browser (e.g. `vite`
// alone for styling work) fall back to a stub so the UI still renders.
const noop = () => {};
const unsub = () => noop;

const stub = {
  platform: 'macos',
  getEngine: async () => ({ status: 'error', message: 'Not running inside Electron.' }),
  restartEngine: async () => ({ status: 'error', message: 'Not running inside Electron.' }),
  onEngineStatus: unsub,
  setPanel: async () => true,
  onPanel: unsub,
  setIgnoreMouse: noop,
  dragStart: noop,
  dragMove: noop,
  dragEnd: noop,
  onShortcut: unsub,
  onMicMuted: unsub,
  setMicMuted: noop,
  getShortcuts: async () => ({
    talk: 'Command+Option+Space',
    stop: 'Command+Option+J',
    panel: 'Command+Option+P',
    hide: 'Command+Option+H',
  }),
  notify: noop,
  getLoginItem: async () => false,
  setLoginItem: async (v) => v,
  onLoginItem: unsub,
  pickFolder: async () => null,
  openLogs: async () => {},
  quit: async () => {},
  getPermissions: async () => [],
  requestPermission: async () => [],
  openPermissionPane: async () => {},
  onPermissions: unsub,
};

export const bridge = window.jarvis || stub;
export const inElectron = !!window.jarvis;

// "Command+Option+Space" -> ["⌘", "⌥", "Space"]
const SYMBOLS = { Command: '⌘', Cmd: '⌘', CommandOrControl: '⌘', Option: '⌥', Alt: '⌥', Control: '⌃', Shift: '⇧' };
export function macKeys(accel) {
  return String(accel || '')
    .split('+')
    .filter(Boolean)
    .map((k) => SYMBOLS[k] || k);
}
