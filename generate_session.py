# Developer by : Mr_Manas_Op
"""Creates a session string for the assistant account.

Run:  python generate_session.py
Use a dedicated Telegram account. The printed string gives full access to that
account, so keep it secret and never commit it.
"""

import asyncio
import os

from dotenv import load_dotenv
from pyrogram import Client


async def main() -> None:
    load_dotenv()
    api_id = int(os.getenv("API_ID") or input("API_ID: ").strip())
    api_hash = os.getenv("API_HASH") or input("API_HASH: ").strip()

    async with Client("session_generator", api_id=api_id, api_hash=api_hash, in_memory=True) as app:
        session = await app.export_session_string()

    print("\nYour session string (put it in .env as SESSION_STRING):\n")
    print(session)
    print("\nKeep it private. Anyone with this string can control the account.")


if __name__ == "__main__":
    asyncio.run(main())
