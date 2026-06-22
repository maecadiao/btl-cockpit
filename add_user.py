"""
Add a new user to auth_config.yaml.

Usage:
  python add_user.py

Prompts for username, name, email, and password, then adds the user.
"""

import bcrypt
import yaml
from pathlib import Path

CONFIG = Path(__file__).parent / "auth_config.yaml"

cfg = yaml.safe_load(CONFIG.read_text())

print("\n── Add BTL Cockpit User ──")
username = input("Username (no spaces): ").strip().lower()
name     = input("Display name: ").strip()
email    = input("Email: ").strip()
password = input("Password: ").strip()

hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

cfg["credentials"]["usernames"][username] = {
    "email": email,
    "name": name,
    "password": hashed,
    "role": "member",
}

CONFIG.write_text(yaml.dump(cfg, default_flow_style=False))
print(f"\nUser '{username}' added. Restart Streamlit to apply.\n")
