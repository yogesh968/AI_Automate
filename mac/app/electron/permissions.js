// macOS privacy permissions Jarvis needs, and shortcuts to the right System Settings panes.
// The engine runs as a child of Jarvis.app, so macOS attributes its mic / screen / automation
// use to Jarvis — granting them here covers the engine too.
const { shell, systemPreferences } = require('electron');

const PANES = {
  microphone: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone',
  accessibility: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility',
  screen: 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture',
  automation: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Automation',
};

const INFO = {
  microphone: { label: 'Microphone', why: '"Hey Jarvis" and voice commands' },
  accessibility: { label: 'Accessibility', why: 'Keyboard, mouse, window and in-app button control' },
  screen: { label: 'Screen Recording', why: 'Seeing your screen ("what\'s this error?")' },
  automation: { label: 'Automation', why: 'Controlling apps like Finder, Music, Notes, Messages' },
};

function status() {
  if (process.platform !== 'darwin') {
    return Object.keys(INFO).map((id) => ({ id, ...INFO[id], status: 'granted' }));
  }
  const mic = systemPreferences.getMediaAccessStatus('microphone');
  const screen = systemPreferences.getMediaAccessStatus('screen');
  const ax = systemPreferences.isTrustedAccessibilityClient(false);
  return [
    { id: 'microphone', ...INFO.microphone, status: mic },
    { id: 'accessibility', ...INFO.accessibility, status: ax ? 'granted' : 'denied' },
    { id: 'screen', ...INFO.screen, status: screen },
    // macOS has no API to query Automation consent; it is asked per app on first use.
    { id: 'automation', ...INFO.automation, status: 'ask-on-use' },
  ];
}

function allGranted() {
  return status().every((p) => p.status === 'granted' || p.status === 'ask-on-use');
}

async function request(id) {
  if (process.platform !== 'darwin') return status();
  if (id === 'microphone') {
    const current = systemPreferences.getMediaAccessStatus('microphone');
    if (current === 'not-determined') {
      await systemPreferences.askForMediaAccess('microphone');
    } else if (current !== 'granted') {
      await shell.openExternal(PANES.microphone);
    }
  } else if (id === 'accessibility') {
    // true = show the system prompt that offers to open Settings
    if (!systemPreferences.isTrustedAccessibilityClient(true)) {
      await shell.openExternal(PANES.accessibility);
    }
  } else if (id === 'screen') {
    // Asking for a capture once makes macOS list Jarvis under Screen Recording.
    try {
      const { desktopCapturer } = require('electron');
      await desktopCapturer.getSources({ types: ['screen'], thumbnailSize: { width: 1, height: 1 } });
    } catch {
      /* ignore — the pane below is what matters */
    }
    if (systemPreferences.getMediaAccessStatus('screen') !== 'granted') {
      await shell.openExternal(PANES.screen);
    }
  } else if (PANES[id]) {
    await shell.openExternal(PANES[id]);
  }
  return status();
}

module.exports = { status, request, allGranted, PANES };
