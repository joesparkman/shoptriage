import ArchitectureDiagram from "./ArchitectureDiagram.jsx";

export default function About() {
  return (
    <section className="panel about">
      <div className="about-block">
        <h2>Origin story</h2>
        <p>
          A local independent auto repair shop handles roughly 200 cars a month, and for years
          relied on one person to answer and triage every incoming call. When that person left,
          the owner and his wife were suddenly buried in voicemails with no system to sort them.
          Customers, including the person building this project, whose own repair had failed,
          waited weeks for a callback that should have taken a day. ShopTriage exists so that
          every voicemail gets classified, routed to the right person, and escalated automatically
          if nobody responds in time. Nothing should fall through the cracks just because one
          person can't answer every phone call.
        </p>
      </div>

      <div className="about-block">
        <h2>Architecture overview</h2>
        <p>
          A voicemail lands in S3 and triggers <code>start_transcription</code>, which starts an
          Amazon Transcribe job and exits immediately, since it never polls. When Transcribe
          finishes, an EventBridge rule hands the transcript to
          <code> process_transcript</code>, which sends it to Claude for classification only:
          category, urgency, whether it's a comeback, and caller details. Claude never decides who
          gets notified; that decision lives entirely in EventBridge rules on a custom bus
          (<code>shop-triage-bus</code>), so the shop can change
          staffing policy without touching the AI prompt.
        </p>
        <p>
          Those rules fan out to SNS (urgent per-role alerts) and SQS with dead-letter queues
          (front-office and vendor calls). Urgent and comeback alerts also kick off a Step
          Functions Standard workflow that emails a staff member an acknowledgment link
          (<code>waitForTaskToken</code>), re-alerts and escalates to the owner on timeout, and
          marks the call overdue if a second timeout passes with no response. Every stage writes
          a timeline event to a single DynamoDB table (with a GSI for the callback board, so there
          are no table scans anywhere), which an API Gateway HTTP API exposes to this React app: the
          Demo Console, Callback Board, and Staff Inbox you can see in the other tabs.
        </p>
      </div>

      <div className="about-block">
        <h2>How the coding agent was used</h2>
        <p>
          This project was built day-by-day with an AI coding agent doing the implementation:
          first Kiro, then Claude Code (via Anthropic's AWS MCP server) after Kiro's paid upgrade
          failed at checkout mid-project. Every session started by having the agent re-read
          <code> DEVLOG.md</code> so it would only work on the task asked for and not build ahead
          of the plan. The agent wrote the SAM template, all seven Lambda functions, the shared
          Lambda layer, the Step Functions state machine, and this frontend, deploying and
          smoke-testing after every milestone with the <code>shoptriage-agent</code> IAM profile,
          and logging every AWS resource created, every bug hit, and every fix in the DEVLOG as it
          went. Real bugs it found and fixed along the way include a Lambda layer path mismatch,
          an EventBridge/S3 circular CloudFormation dependency, Claude Sonnet 5 wrapping JSON
          responses in markdown fences, and a DynamoDB reserved-keyword collision on{" "}
          <code>ttl</code>.
        </p>
      </div>

      <div className="about-block">
        <h2>v1 vs. v2 architecture</h2>
        <p className="muted">
          v1 was an earlier, headless property-management call-triage project: intake and Claude
          classification only, one fixed-list email, no routing, no acknowledgment, no dead-letter
          queues, and DynamoDB reads via full table scans. Everything highlighted below is new in
          ShopTriage (v2).
        </p>
        <ArchitectureDiagram />
      </div>
    </section>
  );
}
