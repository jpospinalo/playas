#!/usr/bin/env python3
"""Migrate legacy feedback documents from single `rating` field to multi-dimensional `ratings`.

Legacy documents have:
    { rating: int, comment: str | None, ... }

New documents have:
    { ratings: { tone: int, length: int, usability: int, overall: int }, comment: str | None, ... }

This script:
1. Reads all documents from the `feedback` collection.
2. For each doc that has `rating` but no `ratings`, creates `ratings` from the old value.
3. Updates the document: sets `ratings` and deletes `rating`.
4. Logs progress and errors.

Usage:
    uv run python scripts/migrate_feedback_ratings.py --dry-run   # Preview changes
    uv run python scripts/migrate_feedback_ratings.py             # Apply changes
"""

from __future__ import annotations

import argparse
import os
import sys

# Add project root to path so we can import rag modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env from project root before importing anything that needs env vars
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass  # dotenv not available, env vars must be set manually


def get_db():
    """Initialize Firebase Admin and return Firestore async client."""
    from rag.api.firebase_admin import get_db

    return get_db()


async def migrate(dry_run: bool = False) -> None:
    db = get_db()
    collection_ref = db.collection("feedback")

    docs = [doc async for doc in collection_ref.stream()]
    migrated = 0
    skipped = 0
    errors = 0

    print(f"Found {len(docs)} feedback documents.")

    for doc in docs:
        data = doc.to_dict() or {}

        # Skip if already migrated
        if "ratings" in data and "rating" not in data:
            skipped += 1
            continue

        # Skip if no rating field at all (shouldn't happen)
        if "rating" not in data:
            print(f"  [SKIP] {doc.id}: no 'rating' field and no 'ratings' field")
            skipped += 1
            continue

        old_rating = data["rating"]
        if not isinstance(old_rating, int) or not (1 <= old_rating <= 5):
            print(f"  [WARN] {doc.id}: invalid rating value {old_rating!r}, defaulting to 3")
            old_rating = 3

        new_ratings = {
            "tone": old_rating,
            "length": old_rating,
            "usability": old_rating,
            "overall": old_rating,
        }

        if dry_run:
            print(f"  [DRY-RUN] {doc.id}: rating={old_rating} → ratings={new_ratings}")
        else:
            try:
                await doc.reference.update(
                    {
                        "ratings": new_ratings,
                        "rating": firestore.DELETE_FIELD,
                    }
                )
                print(f"  [MIGRATED] {doc.id}: rating={old_rating} → ratings={new_ratings}")
            except Exception as exc:
                print(f"  [ERROR] {doc.id}: {exc}")
                errors += 1
                continue

        migrated += 1

    print(f"\nDone: {migrated} migrated, {skipped} skipped, {errors} errors.")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate feedback ratings from single field to multi-dimensional"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without writing to Firestore"
    )
    args = parser.parse_args()

    import asyncio

    # We need firestore.DELETE_FIELD available
    global firestore
    from google.cloud import firestore_v1 as firestore

    asyncio.run(migrate(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
