// Matches scripts/make_samples.py — the only sample_ids demo_trigger accepts.
export const SAMPLES = [
  { id: "breakdown_tow", label: "Breakdown / Tow", blurb: "Car dead on the highway shoulder, smoking, needs a tow now." },
  { id: "comeback", label: "Comeback", blurb: "Alternator job two weeks ago, battery light is back, frustrated caller." },
  { id: "repair_status", label: "Repair Status", blurb: "Checking if a brake job is finished." },
  { id: "billing", label: "Billing", blurb: "Double-charged on a credit card for an oil change." },
  { id: "parts_vendor", label: "Parts Vendor", blurb: "Vendor calling about a backordered part." },
  { id: "spam_other", label: "Spam / Other", blurb: "Extended warranty robocall." },
];

// Roles the escalation workflow and inbox_writer can address.
export const ROLES = ["oncall", "owner", "front_office"];

// Calls in these statuses are still "open" and belong on the callback board.
export const ACTIVE_STATUSES = ["new", "needs_review", "routed", "acknowledged", "overdue"];

export const URGENCY_COLORS = {
  emergency: "#f85149",
  high: "#d29922",
  normal: "#58a6ff",
  low: "#8b949e",
};

export const STATUS_LABELS = {
  new: "New",
  needs_review: "Needs Review",
  routed: "Routed",
  acknowledged: "Acknowledged",
  overdue: "Overdue",
  called_back: "Called Back",
  resolved: "Resolved",
};

export const STAGE_LABELS = {
  uploaded: "Voicemail uploaded",
  transcribing: "Transcribing",
  classified: "Classified",
  routed: "Routed",
  notified: "Staff notified",
  acknowledged: "Acknowledged",
  escalated: "Escalated",
  overdue: "Overdue, unacknowledged",
  summary_failed: "Classification failed",
  called_back: "Marked called back",
  resolved: "Marked resolved",
  note: "Note added",
  attempt: "Callback attempt",
};

export const OUTCOME_LABELS = {
  reached: "Reached them",
  no_answer: "No answer",
};

// Friendly names for the routing_channel values written by routing_dispatcher.
export const CHANNEL_LABELS = {
  oncall_and_owner: "On-call + owner",
  owner_alerts: "Owner",
  front_office_queue: "Front office",
  vendor_queue: "Vendor queue",
  logged_only: "Logged only",
};

export const CATEGORY_LABELS = {
  breakdown_tow: "Breakdown / tow",
  comeback: "Comeback",
  repair_status: "Repair status",
  scheduling: "Scheduling",
  billing: "Billing",
  estimate: "Estimate",
  parts_vendor: "Parts vendor",
  spam_other: "Spam / other",
};

export const STATUS_COLORS = {
  new: "#58a6ff",
  needs_review: "#d29922",
  routed: "#58a6ff",
  acknowledged: "#3fb950",
  overdue: "#f85149",
  called_back: "#3fb950",
  resolved: "#8b949e",
};
