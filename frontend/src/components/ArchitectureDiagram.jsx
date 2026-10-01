// Pure HTML/CSS recreation of docs/architecture-comparison.mmd. Rendered as
// real markup instead of a client-side-rendered Mermaid SVG — no
// font-loading races, no foreignObject/CSS-cascade quirks. The only assets
// are the small static service icons in public/icons/. If the source diagram changes, this needs to be updated by hand
// alongside it (and alongside the README's Mermaid copy) — three places to
// keep in sync in exchange for zero rendering fragility in any of them.

// Icons follow the portfolio's food-scanner architecture page: the official
// AWS Architecture Icons (48px), served as static files from public/icons/.
// Each file already carries its own colored square, so the <img> just sizes
// it. Claude has no AWS badge, so it gets a light square from CSS; React has
// no icon file at all, so it stays an inline SVG badge.
const ICON_BASE = `${import.meta.env.BASE_URL}icons/`;

const FILE_ICONS = {
  s3: "s3.svg",
  lambda: "lambda.svg",
  transcribe: "transcribe.svg",
  eventbridge: "eventbridge.svg",
  rules: "eventbridge.svg",
  sns: "sns.svg",
  stepfunctions: "step-functions.svg",
  sqs: "sqs.svg",
  dynamodb: "dynamodb.svg",
  apigateway: "api-gateway.svg",
  ses: "ses.svg",
  cloudwatch: "cloudwatch.svg",
  claude: "anthropic.svg",
};

const reactBadge = (
  <span className="arch-node-icon" style={{ background: "#149ECA" }}>
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="white"
      strokeWidth="1.3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <ellipse cx="12" cy="12" rx="9" ry="3.6" />
      <ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(60 12 12)" />
      <ellipse cx="12" cy="12" rx="9" ry="3.6" transform="rotate(120 12 12)" />
      <circle cx="12" cy="12" r="1.4" fill="white" stroke="none" />
    </svg>
  </span>
);

// GoTo Connect is the phone system v1 records calls from: not an AWS service, so no icon file.
const phoneBadge = (
  <span className="arch-node-icon" style={{ background: "#546e7a" }}>
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="white"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 4c0 9.4 6.6 16 16 16l2-4-6-2-2 2c-3-1.4-5.6-4-7-7l2-2-2-6z" />
    </svg>
  </span>
);

function Badge({ icon }) {
  if (icon === "react") return reactBadge;
  if (icon === "phone") return phoneBadge;
  const file = FILE_ICONS[icon];
  if (!file) return null;
  const classes = ["arch-node-icon"];
  if (icon === "claude") classes.push("arch-node-icon--plain");
  return (
    <img
      className={classes.join(" ")}
      src={`${ICON_BASE}${file}`}
      alt=""
      aria-hidden="true"
    />
  );
}

function Node({ children, variant, icon }) {
  const classes = ["arch-node"];
  if (variant === "new") classes.push("arch-node--new");
  return (
    <div className={classes.join(" ")}>
      {icon ? (
        <span className="arch-node-body">
          <Badge icon={icon} />
          <span>{children}</span>
        </span>
      ) : (
        children
      )}
    </div>
  );
}

function Arrow() {
  return <div className="arch-arrow" aria-hidden="true" />;
}

function Branch({ children }) {
  return <div className="arch-branch">{children}</div>;
}

function BranchColumn({ children }) {
  return <div className="arch-branch-col">{children}</div>;
}

export default function ArchitectureDiagram() {
  return (
    <>
      <div className="arch-legend" aria-label="Diagram legend">
        <span className="arch-legend-item">
          <span className="arch-legend-swatch" />
          Same as v1
        </span>
        <span className="arch-legend-item">
          <span className="arch-legend-swatch arch-legend-swatch--new" />
          New in v2
        </span>
      </div>
      <div className="arch-wrap">
      <div className="arch-column arch-column--wide">
        <h3 className="arch-title">v2: ShopTriage (this project)</h3>
        <div className="arch-flow">
          <Node icon="s3">S3: voicemail upload</Node>
          <Arrow />
          <Node icon="lambda">start_transcription</Node>
          <Arrow />
          <Node icon="transcribe">Amazon Transcribe</Node>
          <Arrow />
          <Node icon="eventbridge">EventBridge default bus</Node>
          <Arrow />
          <Node icon="lambda">process_transcript</Node>
          <Arrow />
          <Node icon="claude">Claude: classify only (never decides routing)</Node>
          <Arrow />
          <Node variant="new" icon="dynamodb">
            DynamoDB single table + GSI1, no Scans
          </Node>
          <Arrow />
          <Node variant="new" icon="eventbridge">
            shop-triage-bus custom EventBridge bus + archive
          </Node>
          <Arrow />
          <Node variant="new" icon="rules">Routing rules by category / urgency</Node>
          <Arrow />
          <Branch>
            <BranchColumn>
              <Node variant="new" icon="lambda">
                routing_dispatcher: marks routed, starts escalation
              </Node>
              <Arrow />
              <Node variant="new" icon="stepfunctions">
                Step Functions escalation + acknowledgment
              </Node>
              <Arrow />
              <Node variant="new" icon="lambda">send_alert</Node>
              <Arrow />
              <Node variant="new" icon="ses">
                SES: alert email with Acknowledge link
              </Node>
            </BranchColumn>
            <BranchColumn>
              <Node variant="new" icon="sns">SNS: oncall / owner alert topics</Node>
            </BranchColumn>
            <BranchColumn>
              <Node variant="new" icon="sqs">
                SQS + DLQ (front office / vendor queues)
              </Node>
              <Arrow />
              <Node variant="new" icon="cloudwatch">CloudWatch alarm: DLQ depth</Node>
            </BranchColumn>
            <BranchColumn>
              <Node variant="new" icon="cloudwatch">
                CloudWatch Logs: spam calls, log only
              </Node>
            </BranchColumn>
          </Branch>

          <div className="arch-subtitle">Web app: viewing calls</div>
          <Node variant="new" icon="react">
            React web app (demo console / callback board / staff inbox)
          </Node>
          <Arrow />
          <Node variant="new" icon="apigateway">
            API Gateway HTTP API (incl. GET /ack)
          </Node>
          <Arrow />
          <Node variant="new" icon="lambda">api_handler</Node>
          <Arrow />
          <Node variant="new" icon="dynamodb">DynamoDB: Query on GSI1</Node>
        </div>
      </div>

      <div className="arch-column">
        <h3 className="arch-title">v1: Property Management Call Triage (headless)</h3>
        <div className="arch-flow">
          <Node icon="phone">GoTo Connect: tenant call recorded and dropped as an audio file</Node>
          <Arrow />
          <Node icon="s3">S3: recordings/ (existing bucket, left untouched)</Node>
          <Arrow />
          <Node icon="lambda">start_transcription</Node>
          <Arrow />
          <Node icon="transcribe">Amazon Transcribe</Node>
          <Arrow />
          <Node icon="eventbridge">EventBridge: Transcribe job state change</Node>
          <Arrow />
          <Node icon="lambda">process_transcript (also saves a plain-text copy to an archive bucket)</Node>
          <Arrow />
          <Node icon="claude">Claude: category, urgency flags, summary, action items</Node>
          <Arrow />
          <Branch>
            <BranchColumn>
              <Node icon="dynamodb">DynamoDB: CallLog (one item per call, Scan-based reads)</Node>
            </BranchColumn>
            <BranchColumn>
              <Node icon="ses">SES: per-call triage email to the property manager</Node>
            </BranchColumn>
          </Branch>

          <div className="arch-subtitle">Weekly digest</div>
          <Node icon="eventbridge">EventBridge: weekly schedule (Monday 08:00)</Node>
          <Arrow />
          <Node icon="lambda">
            weekly_summary (scans the past 7 days of CallLog; Claude writes the highlights)
          </Node>
          <Arrow />
          <Node icon="ses">SES: weekly digest email</Node>
        </div>
      </div>
      </div>
    </>
  );
}
