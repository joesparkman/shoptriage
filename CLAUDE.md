# ShopTriage — Working Rules

## Working rules for you (the agent)

1. **Keep a `DEVLOG.md`** in the repo root. After each work session, add a dated entry: what you built, which AWS resources you created or changed, problems hit, and how we fixed them. I'll use this for my submission write-up, so be specific.
2. Explain each architecture decision briefly as you go. I'm early in my career and need to be able to explain this in interviews.
3. Use **AWS SAM** (Python 3.12) for all infrastructure. Region: `us-east-1`. Tag every resource `project=shoptriage`.
4. **Per-function least-privilege IAM**. No shared catch-all role.
5. Secrets: Anthropic API key in **SSM Parameter Store as a SecureString** (`/shoptriage/anthropic-api-key`), fetched on cold start and cached. Do not use Secrets Manager.
6. Shared code (Claude client, DynamoDB helpers, timeline logger) goes in a **Lambda Layer**.
7. Deploy after every milestone and confirm the public URL still works.
8. Always use the shoptriage-agent AWS profile for every AWS CLI and SAM command.
9. Start each session by reading DEVLOG.md to see what's already built, and only work on the task I ask for. Don't build ahead.
10. Only record verified facts in DEVLOG.md. No estimated numbers or unconfirmed claims. Never include AWS account IDs, API keys, or other secrets in the DEVLOG or README.
11. Never ask me to paste secrets into chat. When a secret is needed, tell me where to enter it myself.
12. Before retrying any AWS command, check whether the previous attempt actually succeeded.
