import { STAGE_LABELS, OUTCOME_LABELS } from "../constants.js";

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour12: false });
  } catch {
    return iso;
  }
}

// Notes and attempts carry human text, so they read as a short quote instead of
// the key/value chips used for pipeline events.
function EventBody({ ev }) {
  const d = ev.detail;
  if (!d) return null;

  if (ev.stage === "note" || ev.stage === "attempt") {
    return (
      <div className="dash-tl-note">
        {ev.stage === "attempt" && (
          <div className="dash-chips">
            <span className={`dash-chip ${d.outcome === "reached" ? "dash-chip-green" : "dash-chip-amber"}`}>
              {OUTCOME_LABELS[d.outcome] || d.outcome}
            </span>
            {d.attempt_number != null && <span className="dash-chip">attempt {d.attempt_number}</span>}
          </div>
        )}
        {d.text && <p>{d.text}</p>}
        {d.author && <span className="dash-tl-author">by {d.author}</span>}
      </div>
    );
  }

  return (
    <div className="dash-chips">
      {Object.entries(d).map(([k, v]) => (
        <span key={k} className="dash-chip">
          {k}: {String(v)}
        </span>
      ))}
    </div>
  );
}

export default function Timeline({ events }) {
  if (!events || events.length === 0) {
    return <p className="dash-empty">Waiting for the first event…</p>;
  }

  return (
    <ol className="dash-timeline">
      {events.map((ev) => (
        <li key={ev.SK} className={`dash-tl-item stage-${ev.stage}`}>
          <span className="dash-tl-dot" />
          <div>
            <div className="dash-tl-row">
              <strong>{STAGE_LABELS[ev.stage] || ev.stage}</strong>
              <span>{formatTime(ev.ts)}</span>
            </div>
            <EventBody ev={ev} />
          </div>
        </li>
      ))}
    </ol>
  );
}
