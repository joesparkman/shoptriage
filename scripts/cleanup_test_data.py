"""One-shot script to delete all test data from the shoptriage DynamoDB table."""
import boto3
import sys

TABLE = "shoptriage"
REGION = "us-east-1"
PROFILE = "shoptriage-agent"

# All items to delete: (PK, SK)
ITEMS = [
    # Day 2 stuck calls — status=new, stage=uploaded
    ("CALL#a2312d3e-5166-4f27-bb3b-a2c1f0e205ce", "META"),
    ("CALL#a2312d3e-5166-4f27-bb3b-a2c1f0e205ce", "EVENT#2026-09-25T17:53:30.283469+00:00#uploaded"),
    ("CALL#3f546431-2be8-4c20-8cde-c5b09d7c01eb", "META"),
    ("CALL#3f546431-2be8-4c20-8cde-c5b09d7c01eb", "EVENT#2026-09-25T17:52:17.358975+00:00#uploaded"),
    ("CALL#20a346e8-5eef-454c-9518-ea62c77e8aaa", "META"),
    ("CALL#20a346e8-5eef-454c-9518-ea62c77e8aaa", "EVENT#2026-09-25T17:55:18.697573+00:00#uploaded"),
    ("CALL#b8b114b5-eff3-4899-8dc5-7eef17904d7c", "META"),
    ("CALL#b8b114b5-eff3-4899-8dc5-7eef17904d7c", "EVENT#2026-09-25T17:52:35.983359+00:00#uploaded"),
    # Day 3 smoke-test record — META + 4 EVENT items
    ("CALL#smoke-test-day3", "META"),
    ("CALL#smoke-test-day3", "EVENT#2026-09-26T21:22:03.384036+00:00#routed"),
    ("CALL#smoke-test-day3", "EVENT#2026-09-26T21:22:48.530091+00:00#routed"),
    ("CALL#smoke-test-day3", "EVENT#2026-09-26T21:23:43.274167+00:00#routed"),
    ("CALL#smoke-test-day3", "EVENT#2026-09-26T21:23:49.809949+00:00#routed"),
]

session = boto3.Session(profile_name=PROFILE, region_name=REGION)
ddb = session.resource("dynamodb")
table = ddb.Table(TABLE)

ok = 0
err = 0
for pk, sk in ITEMS:
    try:
        table.delete_item(Key={"PK": pk, "SK": sk})
        print(f"DELETED  {pk}  |  {sk}")
        ok += 1
    except Exception as e:
        print(f"ERROR    {pk}  |  {sk}  →  {e}", file=sys.stderr)
        err += 1

print(f"\nSummary: {ok} deleted, {err} errors")

# Verify table is now empty
resp = table.scan(Select="COUNT")
print(f"Table item count after cleanup: {resp['Count']}")
