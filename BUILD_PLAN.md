## Who I am and what we're building

I'm a cloud application developer entering the AWS Zero to Shipped hackathon (due **October 2, 2026, 11:59 PM PT**). The app must be **live on AWS at a public URL** or it's disqualified, so we deploy early and keep it deployable at every step.

**ShopTriage** is an AI call-triage and routing system for small independent auto repair shops. Origin story: a local shop handles ~200 cars/month and relied on one person to filter every call. When that person left, the owner and his wife were buried in voicemails, and customers (including me, with a repair that failed) waited weeks for callbacks. ShopTriage makes sure every voicemail is classified, routed to the right person, and escalated if nobody responds.

Category: **Commercial Potential**. Lane: **Startup**.

## Working rules for you (the agent)

1. **Keep a `DEVLOG.md`** in the repo root. After each work session, add a dated entry: what you built, which AWS resources you created or changed, problems hit, and how we fixed them. I'll use this for my submission write-up, so be specific.
2. Explain each architecture decision briefly as you go. I'm early in my career and need to be able to explain this in interviews.
3. Use **AWS SAM** (Python 3.12) for all infrastructure. Region: `us-east-1`. Tag every resource `project=shoptriage`.
4. **Per-function least-privilege IAM**. No shared catch-all role.
5. Secrets: Anthropic API key in **SSM Parameter Store as a SecureString** (`/shoptriage/anthropic-api-key`), fetched on cold start and cached. Do not use Secrets Manager.
6. Shared code (Claude client, DynamoDB helpers, timeline logger) goes in a **Lambda Layer**.
7. Deploy after every milestone and confirm the public URL still works.
8. Always use the shoptriage-agent AWS profile for every AWS CLI and SAM command.

## Architecture

### Intake and classification
- **S3 bucket `shoptriage-voicemails`**: incoming audio. ObjectCreated triggers `start_transcription`.
- **`start_transcription` Lambda**: validates the file, mints a `call_id`, starts a tagged Amazon Transcribe job, writes a timeline event, and exits without polling.
- **EventBridge rule (default bus)** on Transcribe "Job State Change" = COMPLETED → `process_transcript`.
- **`process_transcript` Lambda**: flattens the transcript, sends it to Claude (model `claude-sonnet-5`; verify the current model string in Anthropic's docs), and gets back strict JSON:
  - `category`: `comeback` | `breakdown_tow` | `repair_status` | `scheduling` | `estimate` | `billing` | `parts_vendor` | `spam_other`
  - `urgency`: `emergency` | `high` | `normal` | `low`
  - `is_comeback`: boolean. True when the caller mentions a recent repair plus the same or a related problem.
  - `caller_name`, `callback_number`, `vehicle`, `summary`, `action_items[]`
  - Validate the JSON. If Claude fails, save the transcript anyway, set status `needs_review`, and log `summary_failed`.
- It writes the call to DynamoDB, then publishes a `CallTriaged` event to the custom bus.

**Important design rule:** Claude only classifies. It never decides who gets the call. Routing lives in EventBridge rules so the shop can change staffing without touching the AI.

### Routing (custom bus `shop-triage-bus`, source `autoshop.triage`)
1. `urgency = emergency` → SNS topic `oncall-alerts` + start escalation (ack window: 15 min; demo mode: 60 sec).
2. `is_comeback = true` AND urgency anything-but `emergency` → SNS topic `owner-alerts` + start escalation (ack window: 2 hr; demo mode: 90 sec).
3. category in `repair_status`, `scheduling`, `billing`, `estimate` → SQS `front-office-queue` → Lambda updates the callback board. Twice-daily digest via EventBridge Scheduler.
4. `parts_vendor` → SQS `vendor-queue`, no alert.
5. `spam_other` → logged only.
6. **EventBridge archive** of all events on the bus, for replay testing.

Every SQS queue gets a **dead-letter queue**. Add a CloudWatch alarm on DLQ depth.

### Escalation (Step Functions Standard workflow)
- Notify the assigned role with an **Acknowledge** link using the `waitForTaskToken` pattern.
- The link hits an API Gateway route → Lambda calls `SendTaskSuccess`, sets status `acknowledged`, records who and when.
- On timeout: re-alert and escalate to the owner. On second timeout: set status `overdue`.
- Statuses: `new` → `acknowledged` → `called_back` → `resolved` (plus `overdue`, `needs_review`).
- Timeouts come from an input field so demo mode can use seconds instead of hours.

### Notifications
- **Do not use SMS.** US SMS needs 10DLC or toll-free registration that won't be approved in time.
- Staff alerts go out as **email via SES** (verified addresses only) and are also written to DynamoDB so the web app's **Staff Inbox** panel shows them live.

### Data (DynamoDB single table `shoptriage`)
- `PK = CALL#<call_id>`, `SK = META` → call record (category, urgency, status, assigned_role, summary, received_at, acknowledged_at...)
- `PK = CALL#<call_id>`, `SK = EVENT#<iso_ts>#<stage>` → timeline entries for the demo console
- `PK = INBOX#<role>`, `SK = <iso_ts>#<call_id>` → staff inbox notifications
- **GSI1**: `status` (PK) + `received_at` (SK) for the callback board. No Scans.
- **TTL** of 7 days on demo data.

### API (API Gateway HTTP API)
- `POST /demo/calls` body `{ "sample_id": "..." }` → copies a pre-made sample voicemail into the intake bucket. **No public file uploads**, only the preset samples.
- `GET /calls?status=...` → callback board (via GSI1)
- `GET /calls/{id}/timeline` → stage-by-stage events
- `GET /inbox/{role}` → staff inbox
- `GET /ack?token=...` → acknowledge an alert
- `POST /calls/{id}/status` → mark `called_back` / `resolved`
- Throttling: rate 2 req/sec, burst 5. Add a simple daily cap on `/demo/calls` (counter item in DynamoDB) to protect cost.

### Sample voicemails
Generate them with **Amazon Polly** via a one-time script (`scripts/make_samples.py`), stored in `shoptriage-samples`. Keep each under 30 seconds. Use these scripts:
1. **Tow/breakdown**: "Hi, my car died on 285 near exit 33, it's smoking from the hood, I need a tow as soon as possible."
2. **Comeback**: "Hey, this is Joe, you replaced my alternator two weeks ago and the battery light is back on. I've called a couple of times, please call me back."
3. **Status check**: "Hi, just checking if my Camry is ready, I dropped it off Monday for brakes."
4. **Billing**: "I think I was charged twice on my card for last week's oil change."
5. **Parts vendor**: "This is Metro Auto Parts, the rotors you ordered are backordered until Friday."
6. **Spam**: "Congratulations, your vehicle's extended warranty is about to expire..."

### Frontend (React + Vite, hosted on S3 + CloudFront)
- **Demo console**: pick a sample voicemail, send it, watch a live stage-by-stage log (uploaded → transcribing → classified → routed → notified → acknowledged/escalated). Poll the timeline endpoint every 2 seconds.
- **Callback board**: calls grouped by status with a "waiting for" timer; overdue in red; comebacks visually flagged.
- **Staff Inbox**: tabs for Owner, Front Office, On-Call, with Acknowledge buttons.
- **About page**: the origin story, architecture diagram, and how the coding agent was used.
- Style: dark theme, Space Grotesk headings, Inter body text, AWS-style service badges in the log.
- SPA routing fix via CloudFront custom error responses (403/404 → /index.html).

### Cost guardrails
- AWS Budget alarm at $20/month.
- Short samples only, TTL cleanup, API throttling, daily demo cap.

## Build order (deploy at every step)

1. **Day 1:** SAM skeleton, S3 + CloudFront with a placeholder page live at a public URL. Parameter Store secret. DEVLOG started.
2. **Day 2:** Intake pipeline: samples via Polly, `start_transcription`, Transcribe, `process_transcript`, Claude classification, DynamoDB writes, timeline events.
3. **Day 3:** Custom bus, routing rules, SNS topics, SQS queues with DLQs, archive.
4. **Day 4:** Step Functions escalation, ack endpoint, SES emails, staff inbox records.
5. **Day 5:** API routes and frontend: demo console, callback board, staff inbox.
6. **Day 6:** About page, architecture diagram and the **v1 vs. v2 comparison diagram** (Mermaid in README and on the About page), throttling, daily cap, budget alarm.
7. **Day 7:** End-to-end testing of all six samples, edge cases, README polish.
8. **Day 8 (buffer):** Fix bugs, final deploy, confirm the URL works in a private browser window.

## Deliverables
- Working public URL
- **Architecture comparison diagram (required by the hackathon organizers).** A side-by-side of my earlier property management call triage project (v1) and ShopTriage (v2). Include it in the README (Mermaid), on the app's About page, and as an image for the Builder Center submission. Show:
  - **v1:** S3 → start_transcription → Transcribe → EventBridge → process_transcript → Claude → DynamoDB, plus one per-call SES email to a single recipient and a scheduled weekly digest. Headless, no UI, no routing, no acknowledgment, no DLQ, DynamoDB Scan.
  - **v2:** same intake, then → custom EventBridge bus → routing rules by category/urgency → SNS (urgent alerts per role) and SQS with DLQs (front office, vendors) → Step Functions escalation with acknowledgment → DynamoDB with GSI → API Gateway → React web app (demo console, callback board, staff inbox).
  - Visually highlight the parts that are new in v2.
- `README.md`: problem, architecture, AWS services used and why, how to deploy, trade-offs, future work (SMS once registered, real phone system integration, multi-shop SaaS)
- `DEVLOG.md`: full record of how you (the agent) and I built this together
