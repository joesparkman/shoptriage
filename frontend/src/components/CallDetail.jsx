import { useEffect, useState } from "react";
import { addNote, getTimeline, logAttempt } from "../api.js";
import { OUTCOME_LABELS } from "../constants.js";
import Timeline from "./Timeline.jsx";

const AUTHOR_KEY = "shoptriage.author";
const MAX_TEXT = 500;

// Remember who is typing so they don't retype their name on every note.
// Storage can throw (private windows, blocked cookies); the form works without it.
function loadAuthor() {
  try {
    return window.localStorage.getItem(AUTHOR_KEY) || "";
  } catch {
    return "";
  }
}

function saveAuthor(name) {
  try {
    window.localStorage.setItem(AUTHOR_KEY, name);
  } catch {
    // ignore
  }
}

const KINDS = [
  { id: "note", label: "Note" },
  { id: "reached", label: OUTCOME_LABELS.reached },
  { id: "no_answer", label: OUTCOME_LABELS.no_answer },
];

// Expanded panel under a call: its history, plus a form to add a note or log a
// callback attempt. `onChanged` tells the board to refresh counts.
export default function CallDetail({ call, initialKind, onChanged }) {
  const [events, setEvents] = useState(null);
  const [kind, setKind] = useState(initialKind || "note");
  const [text, setText] = useState("");
  const [author, setAuthor] = useState(loadAuthor);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function loadTimeline() {
    try {
      const res = await getTimeline(call.call_id);
      setEvents(res.events);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadTimeline();
  }, [call.call_id]);

  useEffect(() => {
    if (initialKind) setKind(initialKind);
  }, [initialKind]);

  async function handleSave(e) {
    e.preventDefault();
    const trimmed = text.trim();
    if (kind === "note" && !trimmed) {
      setError("Write something to save a note.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const who = author.trim() || undefined;
      if (kind === "note") {
        await addNote(call.call_id, { text: trimmed, author: who });
      } else {
        await logAttempt(call.call_id, { outcome: kind, note: trimmed || undefined, author: who });
      }
      saveAuthor(author.trim());
      setText("");
      await loadTimeline();
      onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="dash-detail">
      <form className="dash-note-form" onSubmit={handleSave}>
        <div className="dash-filters" role="tablist" aria-label="What are you recording?">
          {KINDS.map((k) => (
            <button
              type="button"
              key={k.id}
              role="tab"
              aria-selected={kind === k.id}
              className={`dash-filter ${kind === k.id ? "dash-filter-active" : ""}`}
              onClick={() => setKind(k.id)}
            >
              {k.id === "note" ? k.label : `Attempt: ${k.label.toLowerCase()}`}
            </button>
          ))}
        </div>

        <textarea
          value={text}
          maxLength={MAX_TEXT}
          rows={3}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            kind === "note"
              ? "Add a note, e.g. waiting on the part, call back after 2pm"
              : "Optional note about this attempt"
          }
          aria-label="Note text"
        />

        <div className="dash-note-row">
          <input
            value={author}
            maxLength={40}
            onChange={(e) => setAuthor(e.target.value)}
            placeholder="Your name (optional)"
            aria-label="Your name"
          />
          <span className="dash-time">
            {text.length}/{MAX_TEXT}
          </span>
          <button type="submit" className="dash-save" disabled={busy}>
            {busy ? "Saving…" : kind === "note" ? "Save note" : "Log attempt"}
          </button>
        </div>

        {error && <p className="error">{error}</p>}
      </form>

      {events === null ? <p className="dash-empty">Loading history…</p> : <Timeline events={events} />}
    </div>
  );
}
