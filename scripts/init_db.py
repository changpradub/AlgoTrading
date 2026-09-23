"""
Database Initialization & Migration Runner
Connects to PostgreSQL, runs initial schema migrations, and verifies table creation.
"""

import asyncio
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from db.connection import db_manager


async def main():
    print("=" * 60)
    print("DATABASE INITIALIZATION & MIGRATION")
    print("=" * 60)

    print("Connecting to PostgreSQL...")
    await db_manager.connect()

    if not db_manager.is_connected:
        print("❌ Could not connect to PostgreSQL. Check DB credentials in .env")
        return

    print("✅ Connected to PostgreSQL successfully.")

    print("\nRunning Migration: db/migrations/001_initial_schema.sql...")
    await db_manager.run_migration_file("db/migrations/001_initial_schema.sql")
    print("✅ Migration executed successfully.")

    print("\nVerifying tables created in database...")
    rows = await db_manager.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
    )
    tables = [r["table_name"] for r in rows]
    print(f"✅ Found {len(tables)} tables:")
    for t in tables:
        print(f"  • {t}")

    await db_manager.disconnect()
    print("\nDatabase initialization complete!")


if __name__ == "__main__":
    asyncio.run(main())
