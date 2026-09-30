"""Show the full DynamoDB call record for the most recent routed call."""
import boto3

CALL_ID = "7700bbef-3a0f-44f5-b158-953cc6bf5305"
TABLE = "shoptriage"
PROFILE = "shoptriage-agent"
REGION = "us-east-1"

session = boto3.Session(profile_name=PROFILE, region_name=REGION)
table = session.resource("dynamodb").Table(TABLE)

# META record
meta = table.get_item(Key={"PK": f"CALL#{CALL_ID}", "SK": "META"})["Item"]
print("=== META ===")
for k, v in sorted(meta.items()):
    print(f"  {k}: {v}")

# All timeline events
resp = table.query(
    KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
    ExpressionAttributeValues={":pk": f"CALL#{CALL_ID}", ":prefix": "EVENT#"},
)
print("\n=== TIMELINE ===")
for item in resp["Items"]:
    print(f"  {item['SK']}  stage={item.get('stage')}  detail={item.get('detail', {})}")

# Assertions
print("\n=== ASSERTIONS ===")
checks = [
    ("category", meta.get("category"), "comeback"),
    ("is_comeback", meta.get("is_comeback"), True),
    ("urgency", meta.get("urgency"), "high"),
    ("status", meta.get("status"), "routed"),
    ("routing_channel", meta.get("routing_channel"), "owner_alerts"),
]
all_pass = True
for field, actual, expected in checks:
    ok = actual == expected
    if not ok:
        all_pass = False
    icon = "PASS" if ok else "FAIL"
    print(f"  [{icon}] {field}: {actual!r}  (expected: {expected!r})")

print()
if all_pass:
    print("ALL ASSERTIONS PASSED")
else:
    print("SOME ASSERTIONS FAILED")
