import { useEffect, useRef, useState } from "react";
import { getInbox } from "../api.js";
import { ROLES } from "../constants.js";
import CallCard from "./CallCard.jsx";
import "./dashboard.css";

const POLL_MS = 6000;

const ROLE_LABELS = {
  oncall: "On-call",
  owner: "Owner",
  front_office: "Front office",
};

export default function StaffInbox() {
  const [role, setRole] = useState(ROLES[0]);
  const [items, setItems] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  async function load(r) {
    try {
      const res = await getInbox(r);
      setItems(res.items);
      setLoaded(true);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    setLoaded(false);
    load(role);
    pollRef.current = setInterval(() => load(role), POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [role]);

  return (
    <section className="dash">
      <div className="dash-head">
        <h2>Staff inbox</h2>
        <p>Alerts the escalation workflow has sent to each role.</p>
      </div>

      <div className="dash-filters" role="tablist" aria-label="Choose a role">
        {ROLES.map((r) => (
          <button
            key={r}
            role="tab"
            aria-selected={role === r}
            className={`dash-filter ${role === r ? "dash-filter-active" : ""}`}
            onClick={() => setRole(r)}
          >
            {ROLE_LABELS[r] || r}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}

      <div className="dash-card">
        {!loaded && !error ? (
          <p className="dash-empty">Loading alerts…</p>
        ) : items.length === 0 ? (
          <p className="dash-empty">No alerts for {ROLE_LABELS[role] || role}.</p>
        ) : (
          <ul className="dash-calls">
            {items.map((it) => (
              <CallCard
                key={it.SK}
                call={it}
                when={it.created_at}
                whenLabel="alerted"
                badge={
                  <span
                    className={`status-badge ${
                      it.alert_stage === "escalation" ? "status-overdue" : "status-routed"
                    }`}
                  >
                    {it.alert_stage === "escalation" ? "Escalated alert" : "Primary alert"}
                  </span>
                }
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
