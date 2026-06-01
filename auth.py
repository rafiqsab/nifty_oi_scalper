"""
auth.py
Run this ONCE each morning to get a fresh access token.
It opens the Kite login URL, you paste the request_token from the redirect,
and it writes the access token back to your .env file.

    python auth.py
"""
import os
import re
import webbrowser

from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect

load_dotenv()

API_KEY    = os.getenv("KITE_API_KEY", "")
API_SECRET = os.getenv("KITE_API_SECRET", "")

if not API_KEY or not API_SECRET:
    raise SystemExit("Set KITE_API_KEY and KITE_API_SECRET in your .env first.")

kite     = KiteConnect(api_key=API_KEY)
login_url = kite.login_url()

print(f"\nOpening Kite login…\n{login_url}\n")
webbrowser.open(login_url)

print("After login, Kite redirects to something like:")
print("  https://127.0.0.1/?request_token=XXXX&action=login&status=success")
print()
request_token = input("Paste the request_token from the URL: ").strip()

# strip any accidental query-string noise
request_token = re.sub(r"[^A-Za-z0-9]", "", request_token)

data         = kite.generate_session(request_token, api_secret=API_SECRET)
access_token = data["access_token"]

# persist to .env
set_key(".env", "KITE_ACCESS_TOKEN", access_token)

print(f"\n✅  Access token saved to .env")
print(f"   KITE_ACCESS_TOKEN={access_token[:8]}…")
print("\nYou can now run:  python main.py\n")
