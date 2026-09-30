// Remembers where the orb sits on screen between launches.
const fs = require('fs');
const path = require('path');
const { app } = require('electron');

function stateFile() {
  return path.join(app.getPath('userData'), 'window-state.json');
}

function load() {
  try {
    return JSON.parse(fs.readFileSync(stateFile(), 'utf8'));
  } catch {
    return {};
  }
}

function save(state) {
  try {
    fs.mkdirSync(path.dirname(stateFile()), { recursive: true });
    fs.writeFileSync(stateFile(), JSON.stringify(state, null, 2));
  } catch (err) {
    console.error('[windowState] save failed:', err.message);
  }
}

module.exports = { load, save };
