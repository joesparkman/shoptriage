#!/usr/bin/env python3
"""
scripts/make_samples.py
───────────────────────
Generate six sample voicemail MP3s with Amazon Polly and upload them to
the shoptriage-samples S3 bucket.

Run once (or whenever you want to regenerate):
    python scripts/make_samples.py --profile shoptriage-agent

The script is idempotent — it overwrites existing files in S3.
Each clip is kept under 30 seconds to limit Transcribe cost.
"""

import argparse
import io
import logging
import sys
import time

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Sample scripts ─────────────────────────────────────────────────────────
# Keys are the S3 object keys that the demo trigger will reference.
SAMPLES = {
    "breakdown_tow.mp3": (
        "Hi, my name is Marcus. My car just died on 285 near exit 33, "
        "it's smoking from the hood and I'm on the shoulder. "
        "I need a tow as soon as possible. Please call me back at 404-555-0192. Thank you."
    ),
    "comeback.mp3": (
        "Hey, this is Joe Hernandez. You guys replaced my alternator about two weeks ago "
        "and the battery light is back on again. I've called a couple of times and left messages "
        "but nobody's called me back. My number is 770-555-0147. Please call me back."
    ),
    "repair_status.mp3": (
        "Hi, this is Sarah. I'm just calling to check if my Camry is ready. "
        "I dropped it off Monday for a brake job. "
        "My number is 678-555-0231. Thanks."
    ),
    "billing.mp3": (
        "Hi, my name is David Park. I think I was charged twice on my credit card "
        "for last week's oil change. I see two charges for 79 dollars on the same day. "
        "Can someone please look into that and call me back? My number is 404-555-0318."
    ),
    "parts_vendor.mp3": (
        "Hi, this is Kevin from Metro Auto Parts. "
        "I'm calling to let you know the rotors you ordered for the Johnson vehicle "
        "are on backorder and won't be in until Friday. "
        "Give us a call if you need to make other arrangements. Thanks."
    ),
    "spam_other.mp3": (
        "Congratulations! This is an important message regarding your vehicle's extended warranty. "
        "Your factory warranty is about to expire and you may no longer be covered. "
        "Press one now to speak with a warranty specialist before it's too late."
    ),
}

REGION = "us-east-1"
VOICE_ID = "Joanna"   # US English neural voice
ENGINE = "neural"


def get_account_id(session: boto3.Session) -> str:
    sts = session.client("sts")
    return sts.get_caller_identity()["Account"]


def ensure_bucket(s3, bucket_name: str) -> None:
    """Create the bucket if it doesn't exist yet."""
    try:
        s3.head_bucket(Bucket=bucket_name)
        log.info("Bucket %s already exists.", bucket_name)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("404", "NoSuchBucket"):
            log.info("Creating bucket %s …", bucket_name)
            # us-east-1 must NOT specify LocationConstraint (AWS quirk)
            s3.create_bucket(Bucket=bucket_name)
            # Block public access
            s3.put_public_access_block(
                Bucket=bucket_name,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            )
            s3.get_waiter("bucket_exists").wait(Bucket=bucket_name)
            log.info("Bucket %s created.", bucket_name)
        else:
            raise


def synthesize_mp3(polly, text: str) -> bytes:
    """Call Polly and return the MP3 bytes."""
    response = polly.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=VOICE_ID,
        Engine=ENGINE,
        SampleRate="22050",
    )
    return response["AudioStream"].read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ShopTriage sample voicemails via Polly.")
    parser.add_argument("--profile", default="shoptriage-agent", help="AWS profile name")
    parser.add_argument("--region", default=REGION)
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    account_id = get_account_id(session)
    bucket_name = f"shoptriage-samples-{account_id}"

    polly = session.client("polly")
    s3 = session.client("s3")

    log.info("Using profile: %s  account: %s  bucket: %s", args.profile, account_id, bucket_name)
    ensure_bucket(s3, bucket_name)

    for key, script in SAMPLES.items():
        log.info("Synthesising %s …", key)
        mp3_bytes = synthesize_mp3(polly, script)
        s3.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=mp3_bytes,
            ContentType="audio/mpeg",
            Metadata={"project": "shoptriage"},
        )
        log.info("  Uploaded %s (%d bytes)", key, len(mp3_bytes))
        time.sleep(0.2)   # avoid Polly rate limiting

    log.info("All %d samples uploaded to s3://%s/", len(SAMPLES), bucket_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
