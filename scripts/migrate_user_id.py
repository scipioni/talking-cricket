"""Script to migrate a user's Telegram ID / Chat ID to a new one.

Usage:
    uv run python scripts/migrate_user_id.py [old_telegram_id] [new_telegram_id] [--force]

Example:
    uv run python scripts/migrate_user_id.py 73496590 6236717943 --force
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def migrate_user(db_path: Path, no_retention_path: Path, old_id: int, new_id: int, force: bool = False) -> bool:
    print(f"Connecting to database at {db_path}...")
    if not db_path.exists():
        print(f"Error: Database file does not exist at {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if old_id exists
        cursor.execute("SELECT id, sesso, peso_obiettivo_kg FROM users WHERE telegram_user_id = ?", (old_id,))
        old_user_row = cursor.fetchone()
        if not old_user_row:
            print(f"Error: Old user with Telegram ID {old_id} not found in database.")
            return False
        old_user_pk, sesso, peso_obiettivo = old_user_row
        print(f"Found old user (id={old_user_pk}, sesso={sesso}, peso_obiettivo={peso_obiettivo} kg).")

        # Check if new_id exists
        cursor.execute("SELECT id FROM users WHERE telegram_user_id = ?", (new_id,))
        new_user_row = cursor.fetchone()

        if new_user_row:
            new_user_pk = new_user_row[0]
            print(f"Warning: New Telegram ID {new_id} already exists in database (id={new_user_pk}).")

            # Check if new user has any logged data
            has_data = False
            entries_counts = {}
            for table in ["food_entries", "weight_entries", "activity_entries", "activity_level_history"]:
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (new_user_pk,))
                count = cursor.fetchone()[0]
                entries_counts[table] = count
                if count > 0:
                    has_data = True

            if has_data:
                for table, count in entries_counts.items():
                    if count > 0:
                        print(f"  - Table {table} has {count} entries associated with the new ID.")
                
                if not force:
                    print("Error: The new user already has active logged data. Cannot merge or overwrite automatically.")
                    print("If you want to OVERWRITE the new user's empty/initial profile with the old user's history, run with the --force flag.")
                    return False
                else:
                    print("Force flag is active. Deleting the new user's empty profile and all of its associated onboarding records...")
                    for table in ["food_entries", "weight_entries", "activity_entries", "activity_level_history", "pending_drafts"]:
                        cursor.execute(f"DELETE FROM {table} WHERE user_id = ?", (new_user_pk,))
                    cursor.execute("DELETE FROM users WHERE id = ?", (new_user_pk,))
            else:
                print("New user has no logged data. Safely deleting the empty new user profile...")
                cursor.execute("DELETE FROM pending_drafts WHERE user_id = ?", (new_user_pk,))
                cursor.execute("DELETE FROM users WHERE id = ?", (new_user_pk,))

        # Update the old user's telegram_user_id to the new one
        cursor.execute("UPDATE users SET telegram_user_id = ? WHERE id = ?", (new_id, old_user_pk))
        conn.commit()
        print(f"Database successfully updated: Telegram ID changed from {old_id} to {new_id} in users table.")

        # Migrate no-retention JSON registry if old_id is present
        if no_retention_path.exists():
            try:
                print(f"Reading no-retention chats file at {no_retention_path}...")
                with no_retention_path.open("r", encoding="utf-8") as f:
                    chat_ids = json.load(f)
                if isinstance(chat_ids, list):
                    if old_id in chat_ids:
                        chat_ids.remove(old_id)
                        if new_id not in chat_ids:
                            chat_ids.append(new_id)
                        with no_retention_path.open("w", encoding="utf-8") as f:
                            json.dump(chat_ids, f)
                        print(f"Updated no-retention registry: migrated ID {old_id} to {new_id}.")
            except Exception as exc:
                print(f"Non-blocking warning: Failed to update no_retention_chats.json: {exc}")

        print("Migration completed successfully!")
        return True

    except Exception as e:
        conn.rollback()
        print(f"An error occurred during migration: {e}")
        return False
    finally:
        conn.close()


def main() -> None:
    # Resolve default paths using same logic as settings
    project_root = Path(__file__).resolve().parents[1]
    db_path = project_root / "data" / "calobot.db"
    no_retention_path = project_root / "data" / "no_retention_chats.json"

    # Default migration values provided by user
    old_id = 73496590
    new_id = 6236717943
    force = False

    # Accept override arguments if provided
    args = sys.argv[1:]
    if "--force" in args:
        force = True
        args.remove("--force")

    if len(args) > 0:
        try:
            old_id = int(args[0])
            if len(args) > 1:
                new_id = int(args[1])
        except ValueError:
            print("Error: Telegram IDs must be integers.")
            print("Usage: uv run python scripts/migrate_user_id.py [old_telegram_id] [new_telegram_id] [--force]")
            sys.exit(1)

    print(f"=== CALOBOT DATA MIGRATION ===")
    print(f"Moving data from Telegram ID: {old_id}")
    print(f"                     to ID: {new_id}")
    print(f"Force overwrite:           {force}")
    print(f"==============================")

    success = migrate_user(db_path, no_retention_path, old_id, new_id, force)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
