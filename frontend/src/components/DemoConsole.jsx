import { useEffect, useRef, useState } from "react";
import { triggerDemoCall, getTimeline } from "../api.js";
import { SAMPLES, STAGE_LABELS } from "../constants.js";
import Timeline from "./Timeline.jsx";
import "./dashboard.css";

const POLL_MS = 4000;

// The happy path, in order; each lights up when its timeline event arrives.
const PIPELINE = ["uploaded", "transcribing", "classified", "routed", "notified", "acknowledged"];

// Left-edge color on each sample card, matching how urgent that call is.
const SAMPLE_ACCENTS = {
  breakdown_tow: "#f85149",
  comeback: "#d29922",
  repair_status: "#58a6ff",
  billing: "#58a6ff",
  parts_vendor: "#8b949e",
  spam_other: "#8b949e",
};

export default function DemoConsole() {
  const [selected, setSelected] = useState(null);
  const [callId, setCallId] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    return () => clearInterval(pollRef.current);
  }, []);

  async function handleTrigger(sampleId) {
    setSelected(sampleId);
    setTriggering(true);
    setError(null);
    setEvents([]);
    clearInterval(pollRef.current);

    try {
      const res = await triggerDemoCall(sampleId);
      setCallId(res.call_id);

      const poll = async () => {
        try {
          const timeline = await getTimeline(res.call_id);
          setEvents(timeline.events);
        } catch (err) {
          // Call record may not exist for the first second or two — ignore
          // 404s while the pipeline is still writing the first event.
        }
      };
      poll();
      pollRef.current = setInterval(poll, POLL_MS);
    } catch (err) {
      setError(err.message);
    } finally {
      setTriggering(false);
    }
  }

  const isDone = events.some((e) =>
    ["overdue", "resolved", "called_back", "summary_failed"].includes(e.stage)
  );
  const isAcked = events.some((e) => e.stage === "acknowledged");
  const reached = new Set(events.map((e) => e.stage));
  const trouble = ["escalated", "overdue", "summary_failed"].filter((st) => reached.has(st));

  return (
    <section className="dash">
      <div className="dash-head">
        <h2>Trigger a sample voicemail</h2>
        <p>
          Copies a pre-recorded sample into the intake pipeline exactly as if a real voicemail had
          arrived, then follows the call live.
        </p>
      </div>

      <div className="dash-samples">
        {SAMPLES.map((s) => (
          <button
            key={s.id}
            className={`dash-sample ${selected === s.id ? "dash-sample-active" : ""}`}
            style={{ "--accent": SAMPLE_ACCENTS[s.id] || "#58a6ff" }}
            onClick={() => handleTrigger(s.id)}
            disabled={triggering}
          >
            <strong>{s.label}</strong>
            <span>{s.blurb}</span>
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}

      {callId && (
        <div className="dash-card">
          <div className="dash-run-head">
            <h2>Call {callId.slice(0, 8)}</h2>
            {!isDone && (
              <span className="dash-live">
                <span className="dot" />
                {isAcked ? "Acknowledged, waiting for wrap-up" : "Live"}
              </span>
            )}
          </div>

          <ol className="dash-stages" aria-label="Pipeline progress">
            {PIPELINE.map((st) => (
              <li key={st} className={reached.has(st) ? "on" : ""}>
                <span className="dash-stage-dot" />
                {STAGE_LABELS[st]}
              </li>
            ))}
          </ol>

          {trouble.length > 0 && (
            <div className="dash-trouble">
              {trouble.map((st) => (
                <span key={st} className="dash-chip dash-chip-red">
                  {STAGE_LABELS[st]}
                </span>
              ))}
            </div>
          )}

          <Timeline events={events} />
        </div>
      )}
    </section>
  );
}
