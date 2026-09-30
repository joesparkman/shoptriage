import { URGENCY_COLORS, CATEGORY_LABELS } from "../constants.js";
import { timeAgo } from "../format.js";

// One call, shown the same way on the callback board and the staff inbox:
// priority dot, who and what, a few chips, then status and actions on the right.
// `extraChips` adds board-only chips (attempt count); `footer` is an expandable panel.
export default function CallCard({ call, when, whenLabel, badge, actions, extraChips, footer }) {
  return (
    <li className="dash-call">
      <span
        className="dash-pri"
        style={{ background: URGENCY_COLORS[call.urgency] || "#8b949e" }}
        title={call.urgency}
      />
      <div className="dash-call-main">
        <div className="dash-who">
          {call.caller_name || "Unknown caller"}
          <span className="dash-phone">{call.callback_number || "no number"}</span>
        </div>
        <div className="dash-what">{call.summary}</div>
        <div className="dash-chips">
          <span className="dash-chip">{CATEGORY_LABELS[call.category] || call.category}</span>
          {call.urgency === "emergency" && <span className="dash-chip dash-chip-red">emergency</span>}
          {call.is_comeback && call.category !== "comeback" && (
            <span className="dash-chip dash-chip-blue">comeback</span>
          )}
          {extraChips}
          <span className="dash-time">
            {whenLabel ? `${whenLabel} ` : ""}
            {timeAgo(when)}
          </span>
        </div>
      </div>
      <div className="dash-call-side">
        {badge}
        {actions}
      </div>
      {footer && <div className="dash-call-footer">{footer}</div>}
    </li>
  );
}
