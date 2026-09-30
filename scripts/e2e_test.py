"""
End-to-end test for the ShopTriage pipeline.

Steps:
  1. Check whether comeback.mp3 already exists in the voicemails bucket
     (idempotent -- skip copy if already there from a prior run).
  2. Copy comeback.mp3 from samples bucket -> voicemails bucket.
  3. Poll for Transcribe job completion (up to 5 min).
  4. Poll for DynamoDB META record to reach status=classified (process_transcript ran).
  5. Poll for DynamoDB META record to reach status=routed (routing_dispatcher ran).
  6. Print the final call record.

Expected result:
  category=comeback, is_comeback=True, urgency=high, status=routed,
  routing_channel=owner_alerts
"""
import sys
# Force UTF-8 output so checkmarks don't crash on Windows cp1252 terminals
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import time
import json
import boto3
from datetime import datetime, timezone

PROFILE        = "shoptriage-agent"
REGION         = "us-east-1"
SAMPLE_KEY     = "comeback.mp3"
DEST_KEY       = "comeback-e2e-test.mp3"   # fixed key so re-runs are idempotent
TABLE          = "shoptriage"

session   = boto3.Session(profile_name=PROFILE, region_name=REGION)
# Bucket names embed the AWS account id; look it up instead of hard-coding it.
ACCOUNT_ID = session.client("sts").get_caller_identity()["Account"]
SAMPLES_BUCKET = f"shoptriage-samples-{ACCOUNT_ID}"
VOICEMAILS_BUCKET = f"shoptriage-voicemails-{ACCOUNT_ID}"
s3        = session.client("s3")
transcribe = session.client("transcribe")
ddb       = session.resource("dynamodb").Table(TABLE)

# ── Helpers ──────────────────────────────────────────────────────────────────

def ts():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def poll(label, fn, timeout=300, interval=10):
    """Call fn() every interval seconds until it returns a truthy value or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = fn()
        if result:
            return result
        print(f"  [{ts()}] {label} — waiting...")
        time.sleep(interval)
    raise TimeoutError(f"Timed out waiting for: {label}")

# ── Step 0: check if a call record already exists for this dest key ───────────

print(f"\n{'='*60}")
print("ShopTriage End-to-End Test")
print(f"{'='*60}\n")

# Check whether a prior successful run already exists in DynamoDB
# (scan for META items with s3_key = DEST_KEY and status != 'new')
existing = ddb.scan(
    FilterExpression="SK = :meta AND s3_key = :key AND #s <> :new",
    ExpressionAttributeValues={
        ":meta": "META",
        ":key": DEST_KEY,
        ":new": "new",
    },
    ExpressionAttributeNames={"#s": "status"},
)
if existing["Items"]:
    item = existing["Items"][0]
    print(f"[SKIP] A completed record for {DEST_KEY} already exists:")
    print(f"  call_id={item.get('call_id')}  status={item.get('status')}")
    print("  Re-using existing result — no new upload.\n")
    call_id = item["call_id"]
    skip_upload = True
else:
    skip_upload = False
    call_id = None

# ── Step 1: Copy comeback.mp3 into voicemails bucket ─────────────────────────

if not skip_upload:
    print(f"[1] Copying s3://{SAMPLES_BUCKET}/{SAMPLE_KEY}")
    print(f"    -> s3://{VOICEMAILS_BUCKET}/{DEST_KEY}")
    s3.copy_object(
        CopySource={"Bucket": SAMPLES_BUCKET, "Key": SAMPLE_KEY},
        Bucket=VOICEMAILS_BUCKET,
        Key=DEST_KEY,
    )
    print(f"    Copy complete at {ts()}\n")
else:
    print(f"[1] SKIPPED — file already processed\n")

# ── Step 2: Find the Transcribe job for this call ─────────────────────────────

print("[2] Waiting for Transcribe job to appear...")

def find_transcribe_job():
    """Find a shoptriage-* job whose OutputBucketName contains our DEST_KEY."""
    # List recent jobs (most recent first)
    jobs = transcribe.list_transcription_jobs(
        Status="IN_PROGRESS",
        JobNameContains="shoptriage-",
    ).get("TranscriptionJobSummaries", [])
    # Also check COMPLETED jobs (Lambda might have finished quickly)
    jobs += transcribe.list_transcription_jobs(
        Status="COMPLETED",
        JobNameContains="shoptriage-",
    ).get("TranscriptionJobSummaries", [])
    # Return the most recently started one (we want the one just created)
    if jobs:
        # Sort by creation time descending
        jobs.sort(key=lambda j: j.get("CreationTime", 0), reverse=True)
        return jobs[0]["TranscriptionJobName"]
    return None

if not skip_upload:
    job_name = poll("Transcribe job appears", find_transcribe_job, timeout=60, interval=5)
    print(f"  Found job: {job_name}")
    # Extract call_id from job name
    call_id = job_name.replace("shoptriage-", "", 1)
    print(f"  call_id: {call_id}\n")
else:
    # Find the job from DynamoDB record
    meta = ddb.get_item(Key={"PK": f"CALL#{call_id}", "SK": "META"})["Item"]
    job_name = meta.get("transcribe_job", f"shoptriage-{call_id}")
    print(f"  job_name: {job_name}")
    print(f"  call_id: {call_id}\n")

# ── Step 3: Wait for Transcribe job to complete ───────────────────────────────

print("[3] Waiting for Transcribe job to complete...")

def transcribe_done():
    resp = transcribe.get_transcription_job(TranscriptionJobName=job_name)
    status = resp["TranscriptionJob"]["TranscriptionJobStatus"]
    if status == "COMPLETED":
        return resp["TranscriptionJob"]
    if status == "FAILED":
        reason = resp["TranscriptionJob"].get("FailureReason", "unknown")
        raise RuntimeError(f"Transcribe job FAILED: {reason}")
    return None

job = poll("Transcribe COMPLETED", transcribe_done, timeout=300, interval=10)
print(f"  ✅ Transcribe COMPLETED at {ts()}")
print(f"  Output URI: {job['Transcript']['TranscriptFileUri']}\n")

# ── Step 4: Wait for process_transcript to classify the call ──────────────────

print("[4] Waiting for process_transcript to classify the call (DynamoDB status → classified or routed)...")

def call_classified():
    resp = ddb.get_item(Key={"PK": f"CALL#{call_id}", "SK": "META"})
    item = resp.get("Item")
    if item and item.get("status") in ("classified", "routed"):
        return item
    return None

meta = poll("status=classified|routed", call_classified, timeout=120, interval=5)
print(f"  ✅ process_transcript complete at {ts()}")
print(f"  category={meta.get('category')}  urgency={meta.get('urgency')}  is_comeback={meta.get('is_comeback')}  status={meta.get('status')}\n")

# ── Step 5: Wait for routing_dispatcher to mark the call routed ───────────────

print("[5] Waiting for routing_dispatcher to mark call routed...")

def call_routed():
    resp = ddb.get_item(Key={"PK": f"CALL#{call_id}", "SK": "META"})
    item = resp.get("Item")
    if item and item.get("status") == "routed":
        return item
    return None

meta = poll("status=routed", call_routed, timeout=60, interval=5)
print(f"  ✅ routing_dispatcher complete at {ts()}")
print(f"  routing_channel={meta.get('routing_channel')}\n")

# ── Step 6: Print final DynamoDB call record ───────────────────────────────────

print("[6] Final DynamoDB call record:")
print(f"  PK              : CALL#{call_id}")
print(f"  status          : {meta.get('status')}")
print(f"  category        : {meta.get('category')}")
print(f"  urgency         : {meta.get('urgency')}")
print(f"  is_comeback     : {meta.get('is_comeback')}")
print(f"  routing_channel : {meta.get('routing_channel')}")
print(f"  caller_name     : {meta.get('caller_name', '(not set)')}")
print(f"  callback_number : {meta.get('callback_number', '(not set)')}")
print(f"  vehicle         : {meta.get('vehicle', '(not set)')}")
print(f"  summary         : {meta.get('summary', '(not set)')}")

# ── Step 7: Assertions ────────────────────────────────────────────────────────

print("\n[7] Assertions:")
failures = []
if meta.get("category") != "comeback":
    failures.append(f"  ❌ category={meta.get('category')} (expected: comeback)")
else:
    print("  ✅ category=comeback")

if meta.get("is_comeback") is not True:
    failures.append(f"  ❌ is_comeback={meta.get('is_comeback')} (expected: True)")
else:
    print("  ✅ is_comeback=True")

if meta.get("urgency") != "high":
    failures.append(f"  ❌ urgency={meta.get('urgency')} (expected: high)")
else:
    print("  ✅ urgency=high")

if meta.get("status") != "routed":
    failures.append(f"  ❌ status={meta.get('status')} (expected: routed)")
else:
    print("  ✅ status=routed")

if meta.get("routing_channel") != "owner_alerts":
    failures.append(f"  ❌ routing_channel={meta.get('routing_channel')} (expected: owner_alerts)")
else:
    print("  ✅ routing_channel=owner_alerts")

if failures:
    print("\nFAILED:")
    for f in failures:
        print(f)
else:
    print("\n✅ ALL ASSERTIONS PASSED — end-to-end pipeline is working correctly.")

print()
