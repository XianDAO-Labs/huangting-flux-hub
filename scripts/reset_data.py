#!/usr/bin/env python3
"""
reset_data.py — Reset all HuangtingFlux Redis data.

Run this script to clear all fabricated/invalid data from the database.
This is part of the v4.0 data integrity fix.

Usage:
    python3 scripts/reset_data.py
    REDIS_URL=redis://... python3 scripts/reset_data.py
"""

import os
import redis

REDIS_URL = os.environ.get("REDIS_URL", None)
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))

def reset_all_data():
    try:
        if REDIS_URL:
            r = redis.from_url(REDIS_URL, decode_responses=True)
        else:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)
        r.ping()
        print("✅ Connected to Redis.")
    except redis.exceptions.ConnectionError as e:
        print(f"❌ Redis connection failed: {e}")
        return

    keys_to_delete = {
        "total_tokens_saved": "string",
        "total_tokens_baseline": "string",
        "tokens_saved_by_task": "hash",
        "total_reports": "string",
        "unique_agents": "set",
        "recent_activities": "list",
    }

    print("\n📊 Current data before reset:")
    for key, key_type in keys_to_delete.items():
        try:
            val = "N/A"
            if key_type == "string":
                val = r.get(key)
            elif key_type == "hash":
                val = r.hgetall(key)
            elif key_type == "list":
                val = r.lrange(key, 0, -1)
            elif key_type == "set":
                val = r.smembers(key)
            print(f"  {key} ({key_type}): {val}")
        except redis.exceptions.ResponseError as e:
            print(f"  {key} ({key_type}): Error reading - {e}")
        except Exception as e:
            print(f"  {key} ({key_type}): Unexpected error - {e}")

    confirm = input("\n⚠️  This will DELETE all network statistics. Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("❌ Reset cancelled.")
        return

    for key in keys_to_delete.keys():
        try:
            r.delete(key)
            print(f"  🗑️  Deleted: {key}")
        except Exception as e:
            print(f"  ❌ Error deleting {key}: {e}")

    # Initialize with clean zero values
    r.set("total_tokens_saved", 0)
    r.set("total_tokens_baseline", 0)
    r.set("total_reports", 0)
    print("\n✅ Data reset complete. All counters initialized to 0.")
    print("   The network will now only accumulate validated, real data.")

if __name__ == "__main__":
    reset_all_data()
