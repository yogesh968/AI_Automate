// The preload bridge. When the renderer is opened in a normal browser (e.g. `vite`
// alone for styling work) fall back to a stub so the UI still renders.
const noop = () => {};
const unsub = () => noop;

const stub = {
  platform: 'windows',
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
    talk: 'Control+Alt+Space',
    stop: 'Control+Alt+J',
    panel: 'Control+Alt+P',
    hide: 'Control+Alt+H',
  }),
  notify: noop,
  getLoginItem: async () => false,
  setLoginItem: async (v) => v,
  onLoginItem: unsub,
  pickFolder: async () => null,
  openLogs: async () => {},
  quit: async () => {},
};

export const bridge = window.jarvis || stub;
export const inElectron = !!window.jarvis;
