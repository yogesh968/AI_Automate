import React, { useEffect, useRef, useState } from 'react';
import { bridge, macKeys } from '../bridge.js';
import PermissionsCard from './PermissionsCard.jsx';

// Defaults from PROTOCOL.md, used until the engine sends real settings.
const DEFAULTS = {
  user_name: '',
  assistant_name: 'Jarvis',
  llm_model: 'openai/gpt-oss-120b',
  fast_model: 'llama-3.1-8b-instant',
  vision_model: 'meta-llama/llama-4-scout-17b-16e-instruct',
  stt_model: 'whisper-large-v3-turbo',
  tts_provider: 'elevenlabs',
  elevenlabs_voice_id: '',
  elevenlabs_model: 'eleven_multilingual_v2',
  edge_voice: 'hi-IN-MadhurNeural',
  speak_replies: true,
  hindi_script: 'devanagari',
  wake_word_enabled: true,
  wake_word_threshold: 0.5,
  dry_run: false,
  allowed_write_dirs: [],
  confirm_by_voice: true,
  start_with_system: true,
  persona: 'classic',
  address_as: 'sir',
  follow_up: true,
  barge_in: true,
  startup_greeting: true,
  proactive_alerts: true,
  auto_memory: true,
  sound_effects: true,
  home_city: '',
};

const LLM_SUGGESTIONS = [
  'openai/gpt-oss-120b',
  'openai/gpt-oss-20b',
  'llama-3.3-70b-versatile',
  'moonshotai/kimi-k2-instruct',
  'llama-3.1-8b-instant',
];
const VISION_SUGGESTIONS = [
  'meta-llama/llama-4-scout-17b-16e-instruct',
  'meta-llama/llama-4-maverick-17b-128e-instruct',
];
const STT_SUGGESTIONS = ['whisper-large-v3-turbo', 'whisper-large-v3'];
const ELEVEN_MODELS = [
  ['eleven_multilingual_v2', 'Multilingual v2 — most natural'],
  ['eleven_flash_v2_5', 'Flash v2.5 — fastest'],
  ['eleven_turbo_v2_5', 'Turbo v2.5 — fast + good'],
  ['eleven_v3', 'v3 — most expressive'],
];
const EDGE_VOICES = [
  ['hi-IN-MadhurNeural', 'Madhur — Hindi, male'],
  ['hi-IN-SwaraNeural', 'Swara — Hindi, female'],
  ['en-IN-PrabhatNeural', 'Prabhat — Indian English, male'],
  ['en-IN-NeerjaNeural', 'Neerja — Indian English, female'],
  ['en-GB-RyanNeural', 'Ryan — British English, male (movie JARVIS feel)'],
  ['en-GB-ThomasNeural', 'Thomas — British English, male'],
];

function Keys({ accel }) {
  if (!accel) return <span className="muted">(unavailable — taken by another app)</span>;
  return macKeys(accel).map((k) => <kbd key={k}>{k}</kbd>);
}

function Section({ title, children }) {
  return (
    <section className="settings-section">
      <h4>{title}</h4>
      {children}
    </section>
  );
}

function Toggle({ label, hint, checked, onChange }) {
  return (
    <div className="field">
      <label className="switch">
        <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="slider" />
        <span>{label}</span>
      </label>
      {hint && <p className="hint">{hint}</p>}
    </div>
  );
}

// Text input that commits on blur / Enter (not on every keystroke).
function TextField({ label, hint, value, onCommit, placeholder, list }) {
  const [draft, setDraft] = useState(value ?? '');
  useEffect(() => setDraft(value ?? ''), [value]);
  const commit = () => {
    if ((draft ?? '') !== (value ?? '')) onCommit(draft.trim());
  };
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input
        className="input"
        value={draft}
        placeholder={placeholder}
        list={list}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
      />
      {hint && <p className="hint">{hint}</p>}
    </div>
  );
}

function Select({ label, hint, value, options, onChange }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
      {hint && <p className="hint">{hint}</p>}
    </div>
  );
}

function KeyField({ label, saved, link, linkText, onSave }) {
  const [value, setValue] = useState('');
  const [show, setShow] = useState(false);
  return (
    <div className="field key-field">
      <div className="key-head">
        <label className="field-label">{label}</label>
        <span className={`key-state ${saved ? 'saved' : 'missing'}`}>{saved ? '✓ Saved' : 'Not set'}</span>
      </div>
      <div className="row gap">
        <input
          className="input"
          type={show ? 'text' : 'password'}
          value={value}
          autoComplete="off"
          spellCheck={false}
          placeholder={saved ? '•••••••• (saved in macOS Keychain)' : 'Paste your key'}
          onChange={(e) => setValue(e.target.value)}
        />
        <button className="btn" onClick={() => setShow((s) => !s)} title={show ? 'Hide' : 'Show'}>
          {show ? '🙈' : '👁'}
        </button>
      </div>
      <div className="row gap">
        <button
          className="btn primary"
          disabled={!value.trim()}
          onClick={() => {
            onSave(value.trim());
            setValue('');
          }}
        >
          Save key
        </button>
        {saved && (
          <button className="btn danger" onClick={() => onSave('')}>
            Remove
          </button>
        )}
        <a className="link" href={link} target="_blank" rel="noreferrer">
          {linkText}
        </a>
      </div>
    </div>
  );
}

export default function SettingsTab({ settings, keys, send, toast, micMuted, onToggleMic, restartEngine }) {
  const s = { ...DEFAULTS, ...(settings || {}) };
  const [loginItem, setLoginItem] = useState(null);
  const [threshold, setThreshold] = useState(s.wake_word_threshold);
  const thresholdTimer = useRef(null);

  useEffect(() => setThreshold(s.wake_word_threshold), [s.wake_word_threshold]);

  const [shortcuts, setShortcuts] = useState({});

  useEffect(() => {
    bridge.getLoginItem().then(setLoginItem);
    bridge.getShortcuts().then((s) => setShortcuts(s || {}));
    return bridge.onLoginItem(setLoginItem);
  }, []);

  const update = (patch) => send({ type: 'update_settings', settings: patch });

  const saveKey = (name, value) => {
    send({ type: 'set_keys', [name]: value });
    toast(value ? 'Key saved' : 'Key removed', name === 'groq' ? 'Groq' : 'ElevenLabs', 'info');
  };

  const setStartup = async (enabled) => {
    const actual = await bridge.setLoginItem(enabled);
    setLoginItem(actual);
    update({ start_with_system: enabled });
  };

  const addFolder = async () => {
    const dir = await bridge.pickFolder();
    if (dir && !s.allowed_write_dirs.includes(dir)) {
      update({ allowed_write_dirs: [...s.allowed_write_dirs, dir] });
    }
  };

  const removeFolder = (dir) => update({ allowed_write_dirs: s.allowed_write_dirs.filter((d) => d !== dir) });

  return (
    <div className="settings">
      <datalist id="llm-models">
        {LLM_SUGGESTIONS.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
      <datalist id="vision-models">
        {VISION_SUGGESTIONS.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
      <datalist id="stt-models">
        {STT_SUGGESTIONS.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>

      <Section title="API keys">
        <KeyField
          label="Groq (brain + speech recognition)"
          saved={keys.groq}
          link="https://console.groq.com/keys"
          linkText="Get a Groq key ↗"
          onSave={(v) => saveKey('groq', v)}
        />
        <KeyField
          label="ElevenLabs (natural voice)"
          saved={keys.elevenlabs}
          link="https://elevenlabs.io/app/settings/api-keys"
          linkText="Get an ElevenLabs key ↗"
          onSave={(v) => saveKey('elevenlabs', v)}
        />
      </Section>

      <Section title="Profile">
        <TextField
          label="Your name"
          hint="Jarvis will call you by this name."
          value={s.user_name}
          placeholder="e.g. Yogesh"
          onCommit={(v) => update({ user_name: v })}
        />
        <TextField
          label="Assistant name"
          value={s.assistant_name}
          placeholder="Jarvis"
          onCommit={(v) => update({ assistant_name: v || 'Jarvis' })}
        />
      </Section>

      <Section title="Personality">
        <Select
          label="Persona"
          value={s.persona}
          options={[
            ['classic', 'Classic JARVIS — composed, witty, calls you “sir”'],
            ['desi', 'Desi friend — casual Hinglish'],
          ]}
          onChange={(v) => update({ persona: v })}
        />
        {s.persona === 'classic' && (
          <TextField
            label="Address me as"
            hint="e.g. sir, boss, Mr. Kumar — or leave empty to use your name."
            value={s.address_as}
            placeholder="sir"
            onCommit={(v) => update({ address_as: v })}
          />
        )}
        <Toggle
          label="Greet me when Jarvis starts"
          hint="“Good evening, sir. All systems are online.”"
          checked={s.startup_greeting}
          onChange={(v) => update({ startup_greeting: v })}
        />
        <Toggle
          label="Proactive alerts"
          hint="Speaks up on low battery, CPU overload, memory pressure and internet drops."
          checked={s.proactive_alerts}
          onChange={(v) => update({ proactive_alerts: v })}
        />
        <Toggle
          label="Learn about me automatically"
          hint="Quietly remembers lasting facts you mention (names, preferences, projects)."
          checked={s.auto_memory}
          onChange={(v) => update({ auto_memory: v })}
        />
        <TextField
          label="Home city (HUD weather)"
          hint="Leave empty to detect from your internet connection."
          value={s.home_city}
          placeholder="e.g. Delhi"
          onCommit={(v) => update({ home_city: v })}
        />
      </Section>

      <Section title="Voice">
        <Toggle label="Speak replies out loud" checked={s.speak_replies} onChange={(v) => update({ speak_replies: v })} />
        <Select
          label="Voice engine"
          value={s.tts_provider}
          options={[
            ['elevenlabs', 'ElevenLabs — premium, most human'],
            ['edge', 'Microsoft neural voices — free (online)'],
          ]}
          hint={s.tts_provider === 'elevenlabs' && !keys.elevenlabs ? 'No ElevenLabs key yet — the free voice is used.' : null}
          onChange={(v) => update({ tts_provider: v })}
        />
        {s.tts_provider === 'elevenlabs' ? (
          <>
            <TextField
              label="ElevenLabs voice ID"
              hint="Copy a voice ID from your ElevenLabs Voice Library. Leave empty for the default voice."
              value={s.elevenlabs_voice_id}
              placeholder="e.g. 21m00Tcm4TlvDq8ikWAM"
              onCommit={(v) => update({ elevenlabs_voice_id: v })}
            />
            <Select
              label="ElevenLabs model"
              value={s.elevenlabs_model}
              options={ELEVEN_MODELS}
              onChange={(v) => update({ elevenlabs_model: v })}
            />
          </>
        ) : (
          <Select label="Free voice" value={s.edge_voice} options={EDGE_VOICES} onChange={(v) => update({ edge_voice: v })} />
        )}
        <Select
          label="Hindi writing style"
          value={s.hindi_script}
          options={[
            ['devanagari', 'देवनागरी — Hindi words in Devanagari (best pronunciation)'],
            ['roman', 'Roman — Hinglish in English letters'],
          ]}
          onChange={(v) => update({ hindi_script: v })}
        />
      </Section>

      <Section title="Listening">
        <Toggle
          label="Wake word “Hey Jarvis”"
          checked={s.wake_word_enabled}
          onChange={(v) => update({ wake_word_enabled: v })}
        />
        <Toggle
          label="Microphone muted"
          hint="Temporarily stops the wake word (also in the menu-bar menu)."
          checked={micMuted}
          onChange={onToggleMic}
        />
        <div className="field">
          <label className="field-label">
            Wake word sensitivity <span className="muted">({Number(threshold).toFixed(2)})</span>
          </label>
          <input
            type="range"
            min="0.1"
            max="0.95"
            step="0.05"
            value={threshold}
            onChange={(e) => {
              const v = Number(e.target.value);
              setThreshold(v);
              clearTimeout(thresholdTimer.current);
              thresholdTimer.current = setTimeout(() => update({ wake_word_threshold: v }), 400);
            }}
          />
          <p className="hint">Lower = wakes more easily (more false triggers). Higher = stricter.</p>
        </div>
        <Toggle
          label="Continuous conversation"
          hint="After Jarvis answers, it keeps listening for a few seconds — just keep talking, no “Hey Jarvis” needed."
          checked={s.follow_up}
          onChange={(v) => update({ follow_up: v })}
        />
        <Toggle
          label="Interrupt with “Hey Jarvis”"
          hint="Say the wake word while Jarvis is talking to cut it off. Turn off if its own voice triggers it."
          checked={s.barge_in}
          onChange={(v) => update({ barge_in: v })}
        />
        <Toggle
          label="HUD sound effects"
          hint="Soft chimes when Jarvis starts and stops listening."
          checked={s.sound_effects}
          onChange={(v) => update({ sound_effects: v })}
        />
      </Section>

      <Section title="Brain (Groq models)">
        <TextField label="Main model" value={s.llm_model} list="llm-models" onCommit={(v) => update({ llm_model: v })} />
        <TextField
          label="Fast model"
          hint="Used for quick, simple replies."
          value={s.fast_model}
          list="llm-models"
          onCommit={(v) => update({ fast_model: v })}
        />
        <TextField
          label="Vision model"
          hint="Used when Jarvis looks at your screen."
          value={s.vision_model}
          list="vision-models"
          onCommit={(v) => update({ vision_model: v })}
        />
        <TextField label="Speech-to-text model" value={s.stt_model} list="stt-models" onCommit={(v) => update({ stt_model: v })} />
      </Section>

      <Section title="Safety">
        <Toggle
          label="Dry-run mode"
          hint="Jarvis explains what it would do but changes nothing."
          checked={s.dry_run}
          onChange={(v) => update({ dry_run: v })}
        />
        <Toggle
          label="Allow voice confirmation"
          hint="Say “haan” / “yes” to approve risky actions instead of clicking."
          checked={s.confirm_by_voice}
          onChange={(v) => update({ confirm_by_voice: v })}
        />
        <div className="field">
          <label className="field-label">Folders Jarvis may change</label>
          {s.allowed_write_dirs.length === 0 ? (
            <p className="hint">Not limited: your whole user folder (system folders are always protected).</p>
          ) : (
            <ul className="folder-list">
              {s.allowed_write_dirs.map((d) => (
                <li key={d}>
                  <span title={d}>{d}</span>
                  <button className="icon-btn" title="Remove" onClick={() => removeFolder(d)}>
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button className="btn" onClick={addFolder}>
            + Add folder
          </button>
        </div>
      </Section>

      <Section title="macOS permissions">
        <PermissionsCard />
      </Section>

      <Section title="System">
        <Toggle
          label="Open Jarvis at login"
          checked={loginItem ?? s.start_with_system}
          onChange={setStartup}
        />
        <div className="row gap wrap">
          <button className="btn" onClick={() => bridge.openLogs()}>
            Open logs
          </button>
          <button className="btn" onClick={restartEngine}>
            Restart engine
          </button>
          <button className="btn danger" onClick={() => bridge.quit()}>
            Quit Jarvis
          </button>
        </div>
        <div className="hint shortcuts">
          {[
            ['talk', 'Talk'],
            ['stop', 'Stop everything'],
            ['panel', 'Show/hide panel'],
            ['hide', 'Hide/show orb'],
            ['hud', 'HUD mode (full screen)'],
          ].map(([action, label]) => (
            <div key={action}>
              <Keys accel={shortcuts[action]} /> {label}
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}
