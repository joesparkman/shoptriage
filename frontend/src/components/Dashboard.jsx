import { useEffect, useState } from "react";
import { getStats } from "../api.js";
import {
  CHANNEL_LABELS,
  STATUS_LABELS,
  STATUS_COLORS,
  URGENCY_COLORS,
} from "../constants.js";
import { timeAgo } from "../format.js";
import Gauge from "./Gauge.jsx";
import Odometer from "./Odometer.jsx";
import "./dashboard.css";

const POLL_MS = 6000;
const ROUTE_COLORS = ["#4aa8ff", "#2fd67b", "#ffb020", "#ff4d2e", "#b58cff"];
const URGENCY_ORDER = ["emergency", "high", "normal", "low"];
const STATUS_ORDER = ["new", "needs_review", "routed", "acknowledged", "overdue", "called_back", "resolved"];

// Time-to-close can be minutes in a tidy demo or hours if calls sit open, so
// the dial switches units instead of pinning the needle at its maximum.
function closeDial(minutes) {
  if (minutes == null) {
    return { min: 0, max: 60, major: 10, minor: 5, redFrom: 30, value: null, shown: "—", unit: "min" };
  }
  if (minutes <= 60) {
    return { min: 0, max: 60, major: 10, minor: 5, redFrom: 30, value: minutes, shown: String(Math.round(minutes)), unit: "min" };
  }
  const hours = minutes / 60;
  return { min: 0, max: 12, major: 2, minor: 1, redFrom: 6, value: hours, shown: hours.toFixed(1), unit: "hours" };
}

const LIGHT_ICONS = {
  urgent: "M12 3L2 21h20L12 3zm1 14h-2v-2h2v2zm0-4h-2V9h2v4z",
  overdue: "M12 2a10 10 0 100 20 10 10 0 000-20zm1 11h-5V7h2v4h3v2z",
  review: "M15.5 14h-.8l-.3-.3A6.5 6.5 0 109.5 16a6.5 6.5 0 004.2-1.6l.3.3v.8l5 5 1.5-1.5-5-5zm-6 0a4.5 4.5 0 110-9 4.5 4.5 0 010 9z",
  comeback: "M7 7h10v3l4-4-4-4v3H5v6h2V7zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2v4z",
};

function WarningLight({ kind, label, count, tone, blink, hint }) {
  const on = count > 0;
  return (
    <div
      className={`dash-light ${on ? `on-${tone}` : ""} ${on && blink ? "blink" : ""}`}
      title={hint}
    >
      <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d={LIGHT_ICONS[kind]} />
      </svg>
      {on && <span className="dash-light-count">{count}</span>}
      <span className="dash-light-tip">{label}</span>
    </div>
  );
}

function SegmentedBar({ segments }) {
  const total = segments.reduce((n, s) => n + s.count, 0);
  if (total === 0) return <p className="dash-empty">No calls yet.</p>;
  return (
    <>
      <div className="dash-seg-bar">
        {segments
          .filter((s) => s.count > 0)
          .map((s) => (
            <i key={s.key} style={{ width: `${(s.count / total) * 100}%`, background: s.color }} title={`${s.label}: ${s.count}`} />
          ))}
      </div>
      <ul className="dash-seg-legend">
        {segments
          .filter((s) => s.count > 0)
          .map((s) => (
            <li key={s.key}>
              <span className="dash-swatch" style={{ background: s.color }} />
              {s.label} <b>{s.count}</b>
            </li>
          ))}
      </ul>
    </>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const s = await getStats();
        if (!cancelled) {
          setStats(s);
          setError(null);
          setNow(Date.now());
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    }
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (!stats) {
    return (
      <section className="dash">
        {error ? <p className="error">Couldn't load stats: {error}</p> : <p className="muted">Loading dashboard…</p>}
      </section>
    );
  }

  const dial = closeDial(stats.avg_close_minutes);
  const lights = stats.lights;
  const routeMax = Math.max(...stats.routes.map((r) => r.count), 1);

  return (
    <section className="dash">
      <div className={`dash-status ${error ? "offline" : ""}`}>
        <span className="dot" />
        {error ? "Reconnecting… showing last data" : `Live · updated ${new Date(stats.generated_at).toLocaleTimeString([], { hour12: false })}`}
      </div>

      <div className="dash-cluster">
        <div className="dash-gauge-wrap">
          <Gauge id="volume" min={0} max={12} major={2} minor={1} redFrom={10} value={stats.calls_last_hour} />
          <div className="dash-gauge-label">Call volume</div>
          <div className="dash-gauge-readout">
            {stats.calls_last_hour}
            <small>calls in the last hour</small>
          </div>
        </div>

        <div className="dash-center">
          <div className="dash-lights">
            <WarningLight kind="urgent" label="Urgent" tone="red" blink count={lights.urgent_unacked} hint="Emergency calls nobody has acknowledged yet" />
            <WarningLight kind="overdue" label="Overdue" tone="red" count={lights.overdue} hint="Calls that ran out the acknowledgment window" />
            <WarningLight kind="review" label="Review" tone="amber" count={lights.needs_review} hint="Voicemails the AI couldn't classify" />
            <WarningLight kind="comeback" label="Comeback" tone="blue" count={lights.open_comebacks} hint="Open calls from customers with a repeat problem" />
          </div>

          <div className="dash-odo-box">
            <div className="dash-odo-title">Calls triaged · last 7 days</div>
            <Odometer value={stats.calls_7d} />
          </div>

          <div className="dash-lcd">
            <span>LAST 24H</span>
            <b>{stats.calls_last_24h}</b>
            <span>OPEN NOW</span>
            <b>{stats.open_count}</b>
            <span>OVERDUE</span>
            <b>{lights.overdue}</b>
          </div>
        </div>

        <div className="dash-gauge-wrap">
          <Gauge
            id="close"
            min={dial.min}
            max={dial.max}
            major={dial.major}
            minor={dial.minor}
            redFrom={dial.redFrom}
            value={dial.value}
          />
          <div className="dash-gauge-label">Time to close</div>
          <div className="dash-gauge-readout">
            {dial.shown}
            <small>{dial.unit} on average{stats.closed_count ? ` (${stats.closed_count} closed)` : ""}</small>
          </div>
        </div>
      </div>

      <div className="dash-minis">
        <div className="dash-mini">
          <h3>Urgency mix · 7 days</h3>
          <SegmentedBar
            segments={URGENCY_ORDER.map((u) => ({
              key: u,
              label: u[0].toUpperCase() + u.slice(1),
              count: stats.by_urgency[u] || 0,
              color: URGENCY_COLORS[u],
            }))}
          />
          <p>How urgent the AI judged each voicemail to be.</p>
        </div>
        <div className="dash-mini">
          <h3>Where calls stand</h3>
          <SegmentedBar
            segments={STATUS_ORDER.map((s) => ({
              key: s,
              label: STATUS_LABELS[s],
              count: stats.by_status[s] || 0,
              color: STATUS_COLORS[s],
            }))}
          />
          <p>Every call from the last 7 days, by its current status.</p>
        </div>
      </div>

      <div className="dash-computer">
        <div className="dash-card">
          <h2>Live call feed</h2>
          {stats.recent.length === 0 ? (
            <p className="dash-empty">No calls yet. Trigger one from the Demo Console.</p>
          ) : (
            <ul className="dash-feed">
              {stats.recent.map((c) => (
                <li key={c.call_id}>
                  <span className="dash-pri" style={{ background: URGENCY_COLORS[c.urgency] || "#8b949e" }} title={c.urgency} />
                  <div>
                    <div className="dash-who">{c.caller_name || "Unknown caller"}</div>
                    <div className="dash-what">{c.summary}</div>
                  </div>
                  <div className="dash-meta">
                    {timeAgo(c.received_at, now)}
                    {c.routing_channel && <> → {CHANNEL_LABELS[c.routing_channel] || c.routing_channel}</>}
                    <br />
                    <span className={`status-badge status-${c.status}`}>{STATUS_LABELS[c.status] || c.status}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="dash-card">
          <h2>Routed to · 7 days</h2>
          {stats.routes.length === 0 ? (
            <p className="dash-empty">Nothing routed yet.</p>
          ) : (
            <div className="dash-routes">
              {stats.routes.map((r, i) => (
                <div key={r.name}>
                  <div className="dash-route-row">
                    <span>{CHANNEL_LABELS[r.name] || r.name}</span>
                    <span>{r.count}</span>
                  </div>
                  <div className="dash-bar">
                    <i style={{ width: `${(r.count / routeMax) * 100}%`, background: ROUTE_COLORS[i % ROUTE_COLORS.length] }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
