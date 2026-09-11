#!/usr/bin/env python3
"""
Converts config.json (plain text) into config.enc (encrypted), then
deletes config.json so your Supabase password no longer sits in plain
text on the device.

Run:
    python encrypt_config.py
"""

import json
import sys
from pathlib import Path

from security import encrypt_config, prompt_passphrase, harden_permissions

CONFIG_JSON = Path(__file__).parent / "config.json"
CONFIG_ENC = Path(__file__).parent / "config.enc"


def main():
    if not CONFIG_JSON.exists():
        print("config.json tidak ditemukan. Buat dulu dari config.example.json.")
        sys.exit(1)

    if CONFIG_ENC.exists():
        confirm = input("config.enc sudah ada. Timpa? (y/N): ").strip().lower()
        if confirm != "y":
            print("Dibatalkan.")
            sys.exit(0)

    plain_config = json.loads(CONFIG_JSON.read_text())

    print("Buat passphrase untuk mengunci config ini.")
    print("Passphrase ini TIDAK disimpan di mana pun — kamu akan diminta")
    print("mengetiknya setiap kali menjalankan ranemax_agent.py.")
    passphrase = prompt_passphrase(confirm=True)

    blob = encrypt_config(plain_config, passphrase)
    CONFIG_ENC.write_bytes(blob)
    harden_permissions(CONFIG_ENC)

    CONFIG_JSON.unlink()
    print(f"\nSelesai. {CONFIG_ENC.name} dibuat, {CONFIG_JSON.name} dihapus.")
    print("Jalankan agent seperti biasa: python ranemax_agent.py")


if __name__ == "__main__":
    main()
