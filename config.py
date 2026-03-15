import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

ALLOWED_GROUP = int(os.getenv("ALLOWED_GROUP", "-1002361694932"))

OWNER_IDS = set()
owner_ids_str = os.getenv("OWNER_IDS", "1077356338")
for owner_id in owner_ids_str.split(","):
    owner_id = owner_id.strip()
    if owner_id.isdigit():
        OWNER_IDS.add(int(owner_id))
