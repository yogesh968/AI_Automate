// System tray icon and menu.
const path = require('path');
const { Tray, Menu, nativeImage } = require('electron');

function createTray(actions) {
  const icon = nativeImage.createFromPath(path.join(__dirname, 'assets', 'tray.png'));
  const tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);
  tray.setToolTip('Jarvis');

  const rebuild = (state) => {
    const menu = Menu.buildFromTemplate([
      { label: 'Jarvis', enabled: false },
      { type: 'separator' },
      {
        label: state.orbVisible ? 'Hide orb' : 'Show orb',
        click: () => actions.toggleOrb(),
      },
      { label: 'Open panel', click: () => actions.openPanel('chat') },
      { label: 'Settings', click: () => actions.openPanel('settings') },
      { type: 'separator' },
      {
        label: 'Mute microphone',
        type: 'checkbox',
        checked: state.micMuted,
        click: (item) => actions.setMicMuted(item.checked),
      },
      {
        label: 'Start with Windows',
        type: 'checkbox',
        checked: state.startWithSystem,
        click: (item) => actions.setStartWithSystem(item.checked),
      },
      { type: 'separator' },
      { label: 'Restart engine', click: () => actions.restartEngine() },
      { label: 'Open logs folder', click: () => actions.openLogs() },
      { type: 'separator' },
      { label: 'Quit Jarvis', click: () => actions.quit() },
    ]);
    tray.setContextMenu(menu);
  };

  tray.on('click', () => actions.toggleOrb(true));
  tray.on('double-click', () => actions.openPanel('chat'));

  return { tray, rebuild };
}

module.exports = { createTray };
