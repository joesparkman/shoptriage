import { useEffect, useRef, useState } from "react";
import { listCallsByStatus, updateCallStatus } from "../api.js";
import { STATUS_LABELS } from "../constants.js";
import { timeAgo } from "../format.js";
import CallCard from "./CallCard.jsx";
import CallDetail from "./CallDetail.jsx";
import "./dashboard.css";

const POLL_MS = 6000;

const FILTERS = [
  { id: "all", label: "All open", test: () => true },
  { id: "urgent", label: "Emergency", test: (c) => c.urgency === "emergency" },
  { id: "overdue", label: "Overdue", test: (c) => c.status === "overdue" },
  { id: "comeback", label: "Comebacks", test: (c) => c.is_comeback },
];

// Reached and no-answer attempts are counted separately: "3 attempts" alone hides
// whether anyone ever got through. Calls logged before the per-outcome counters
// existed may have a total only, so any unexplained remainder shows as plain attempts.
function AttemptChips({ call }) {
  const reached = Number(call.reached_count || 0);
  const noAnswer = Number(call.no_answer_count || 0);
  const total = Number(call.attempt_count || 0);
  const other = Math.max(0, total - reached - noAnswer);
  if (total === 0) return null;
  return (
    <>
      {reached > 0 && (
        <span className="dash-chip dash-chip-green" title="Attempts where you reached them">
          {reached} reached
        </span>
      )}
      {noAnswer > 0 && (
        <span className="dash-chip dash-chip-amber" title="Attempts with no answer">
          {noAnswer} no answer
        </span>
      )}
      {other > 0 && (
        <span className="dash-chip" title="Attempts logged before outcomes were tracked separately">
          {other} attempt{other === 1 ? "" : "s"}
        </span>
      )}
      {call.last_attempt_at && <span className="dash-time">last tried {timeAgo(call.last_attempt_at)}</span>}
    </>
  );
}

export default function CallbackBoard() {
  const [calls, setCalls] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [stale, setStale] = useState(false);
  const loadedRef = useRef(false);
  const [filter, setFilter] = useState("all");
  // Which call's detail panel is open, and which form tab it should start on.
  const [open, setOpen] = useState({ id: null, kind: null });
  const pollRef = useRef(null);

  // One request returns every open call (one request per status was 5x the traffic
  // and tripped the API's old 2 requests/second limit). A failed poll after data is already
  // showing is just "stale": the next poll usually recovers, so don't flash an error.
  async function load() {
    try {
      const res = await listCallsByStatus("open");
      setCalls(res.calls);
      loadedRef.current = true;
      setLoaded(true);
      setStale(false);
      setError(null);
    } catch (err) {
      if (loadedRef.current) setStale(true);
      else setError(err.message);
    }
  }

  useEffect(() => {
    load();
    pollRef.current = setInterval(load, POLL_MS);
    return () => clearInterval(pollRef.current);
  }, []);

  async function handleResolve(callId) {
    setBusyId(callId);
    try {
      await updateCallStatus(callId, "resolved");
      if (open.id === callId) setOpen({ id: null, kind: null });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  function toggle(callId, kind) {
    setOpen((cur) => (cur.id === callId && cur.kind === kind ? { id: null, kind: null } : { id: callId, kind }));
  }

  const active = FILTERS.find((f) => f.id === filter) || FILTERS[0];
  const shown = calls.filter(active.test);

  return (
    <section className="dash">
      <div className="dash-head">
        <h2>Callback board</h2>
        <p>
          Every call still waiting on a callback, newest first. Log each attempt, add notes as you
          go, and resolve the call when it's done.
        </p>
      </div>

      <div className="dash-filters" role="tablist" aria-label="Filter calls">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            role="tab"
            aria-selected={filter === f.id}
            className={`dash-filter ${filter === f.id ? "dash-filter-active" : ""}`}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
            <b>{calls.filter(f.test).length}</b>
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}
      {stale && !error && <p className="dash-stale">Reconnecting… showing the last calls loaded.</p>}

      <div className="dash-card">
        {!loaded && !error ? (
          <p className="dash-empty">Loading calls…</p>
        ) : shown.length === 0 ? (
          <p className="dash-empty">
            {calls.length === 0 ? "Nothing waiting on a callback right now." : "No calls match this filter."}
          </p>
        ) : (
          <ul className="dash-calls">
            {shown.map((c) => {
              const isOpen = open.id === c.call_id;
              return (
                <CallCard
                  key={c.call_id}
                  call={c}
                  when={c.received_at}
                  whenLabel="received"
                  badge={
                    <span className={`status-badge status-${c.status}`}>
                      {STATUS_LABELS[c.status] || c.status}
                    </span>
                  }
                  extraChips={<AttemptChips call={c} />}
                  actions={
                    <div className="dash-actions">
                      <button
                        className={isOpen && open.kind === "details" ? "dash-btn-on" : ""}
                        onClick={() => toggle(c.call_id, "details")}
                        aria-expanded={isOpen && open.kind === "details"}
                      >
                        History &amp; notes
                      </button>
                      <button
                        className={isOpen && open.kind === "no_answer" ? "dash-btn-on" : ""}
                        onClick={() => toggle(c.call_id, "no_answer")}
                      >
                        Log attempt
                      </button>
                      <button disabled={busyId === c.call_id} onClick={() => handleResolve(c.call_id)}>
                        Resolve
                      </button>
                    </div>
                  }
                  footer={
                    isOpen && (
                      <CallDetail
                        call={c}
                        initialKind={open.kind === "details" ? "note" : open.kind}
                        onChanged={load}
                      />
                    )
                  }
                />
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
