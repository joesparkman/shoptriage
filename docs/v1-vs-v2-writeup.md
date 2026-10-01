## The problem

After a repair at a local independent shop, my car still had issues, and I couldn't reach anyone for about two weeks. The shop services roughly 200 cars a month and had let go of the one person who screened every call, leaving the owner and his wife answering phones while running the shop. Voicemails piled up, and customers waited weeks for callbacks that should have taken a day.

## What ShopTriage does

ShopTriage makes sure every voicemail is heard, classified, sent to the right person, and escalated until someone responds.

* **Listen:** Each voicemail is transcribed with Amazon Transcribe.
* **Classify:** Claude reads the transcript and returns the category, urgency, whether it's a comeback (a car returning with the same problem), and caller details. That is its only job.
* **Route:** EventBridge rules decide who gets notified. Emergencies go to on-call staff and the owner, front-office and vendor calls go to their own queues, and robocalls are only logged.
* **Escalate:** Urgent and comeback calls start a Step Functions workflow that emails an acknowledgment link. If nobody clicks in time, it re-alerts, escalates to the owner, and finally marks the call overdue.
* **Track:** A React web app gives the shop a live dashboard, a callback board where staff log each attempt ("reached them" or "no answer") and add notes, and a staff inbox of alerts for each role.

## Key design choice: the AI never decides routing

Claude classifies the call; it never decides who gets alerted. Routing lives in EventBridge rules on a custom bus (`shop-triage-bus`) that are easy to read and audit. The shop can change its staffing policy without touching the AI prompt, and a critical business decision never depends on a model having a good day.

## Architecture

**Intake and classification:** S3 voicemail upload → `start_transcription` Lambda (starts the Transcribe job and exits, no polling) → Amazon Transcribe → EventBridge default bus → `process_transcript` Lambda → Claude (classification only) → DynamoDB single table with GSI1

**Routing and escalation:** `shop-triage-bus` custom EventBridge bus with archive → routing rules by category and urgency:

* `routing_dispatcher` Lambda → Step Functions Standard workflow (`waitForTaskToken`) → `send_alert` Lambda → SES alert email with an Acknowledge link
* SNS on-call and owner alert topics
* SQS with dead-letter queues for front-office and vendor calls, plus a CloudWatch alarm on DLQ depth
* CloudWatch Logs for spam calls (log only)

**Web app:** React → API Gateway HTTP API → `api_handler` Lambda (calls, timeline, inbox, status updates, notes, attempts, stats) → DynamoDB Query on GSI1, with no table scans anywhere. `GET /ack` is served separately by the `escalation_ack` Lambda, which resumes the paused Step Functions execution.

**Infrastructure:** One SAM template, eight Lambda functions (including `demo_trigger`, which seeds a sample voicemail for live demos), and a shared Lambda layer. Every stage writes a timeline event to DynamoDB, so each call has a complete history.

## What's new compared with my earlier project

ShopTriage (v2) is a new build that goes well beyond my earlier headless property-management call triage project (v1).

| | v1: Property management triage | v2: ShopTriage |
| --- | --- | --- |
| Interface | Headless | Dashboard, callback board, staff inbox |
| Alerting | A single Lambda emails one fixed per-call recipient | EventBridge rules route by category and urgency to on-call, owner, front-office, and vendor channels (SNS/SQS) |
| Reporting | Weekly digest email to a fixed manager address | Live dashboard + `/stats` endpoint; no weekly digest yet |
| Acknowledgment | None | Step Functions waits for an acknowledgment click, re-alerts, then escalates to the owner |
| Failure handling | No dead-letter queues | SQS DLQs on front-office/vendor queues (3 retries) with a CloudWatch alarm |
| Data access | Full table scans (single-key table, no GSI) | Single-table design, GSI1 queries only, no scans |
| Callback tracking | None | Logged attempts and notes on every call |

## V1 vs V2 architecture

![A comparison of version one and version two of the ShopTriage app](https://prod-assets.cosmic.aws.dev/a/3K3x51hQ4c0ysWxv9s0DnJXB8jK/Shop.webp?imgSize=1520x4802 "V1 vs V2")

## Results from testing

* About 5 seconds from audio arriving to a fully classified call
* First alert email sent in about 30 seconds
* Escalation timeout of 1 minute for the demo (about 15 minutes in a real shop)

## How the coding agent was used

I built ShopTriage day by day with an AI coding agent doing the implementation: Kiro first, then Claude Code after Kiro's paid upgrade failed at checkout mid-project. Every session started with the agent re-reading `DEVLOG.md` so it only worked on the task at hand. The agent wrote the SAM template, all eight Lambda functions, the shared layer, the Step Functions state machine, and the frontend. It deployed and smoke-tested after every milestone and logged every resource, bug, and fix in the DEVLOG.

Real bugs we worked through:

* A Lambda layer path mismatch
* A circular CloudFormation dependency between EventBridge and S3
* Claude wrapping its JSON responses in markdown fences
* A DynamoDB reserved-keyword collision on `ttl`

The most serious catch came during final testing. I triggered two alerts at once and found that a mangled acknowledgment link could quietly cancel the escalation for a completely different caller's emergency, so it would never reach the owner. I patched the system so every acknowledgment link is strictly verified against the exact call it belongs to. When I ran the same test again, the link was rejected.

## What's next

* Text-message alerts in place of email
* Staff logins
* Secure data separation so one deployment can safely serve multiple shops

## Demo video

<video controls width="100%">
  <source src="https://www.joesparkman.com/ShopTriage_demo_16x9_narrated.mp4" type="video/mp4">
  Your browser does not support the video tag. <a href="https://www.joesparkman.com/ShopTriage_demo_16x9_narrated.mp4">Watch the demo video here</a>.
</video>
