"""Per-member Google sign-in + read-only Gmail for the Inbox Digest.

Each team member signs in with Google once (Workspace-Internal OAuth app,
scopes: openid, email, gmail.readonly). We capture their refresh token,
encrypt it at rest on the persistent volume, and use it to read *only their
own* unread inbox. Identity for the current browser session is a signed,
short-lived token (used for a cookie in app.py) — the OAuth state is signed
statelessly so it survives the redirect round-trip without server session.

Config (env / ~/.claude/.env):
  GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET  — the Web OAuth client
  OAUTH_REDIRECT_URI                                  — https://cockpit.bethelightdecor.com/
  BTL_SESSION_KEY                                     — HMAC key for session/state signing
  BTL_TOKEN_ENC_KEY                                   — Fernet key for token-at-rest
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

# oauthlib complains when Google returns scopes in a different order / adds
# openid; relax so fetch_token doesn't raise on the benign mismatch.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

ALLOWED_DOMAIN = "bethelightdecor.com"   # Internal app already enforces this; belt + suspenders
# One Google connection per member. Read-only scopes for what the cockpit uses;
# add more here as features need them (each new scope re-prompts once).
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]
BTL_TZ = ZoneInfo("America/Chicago")
_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"
SESSION_TTL_SEC = 14 * 24 * 3600   # stay signed in for two weeks


# ── config ────────────────────────────────────────────────────────────────────

def _env(name: str) -> str:
    if val := os.environ.get(name):
        return val
    dot = Path.home() / ".claude" / ".env"
    try:
        for raw in dot.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def is_configured() -> bool:
    return bool(_env("GOOGLE_OAUTH_CLIENT_ID") and _env("GOOGLE_OAUTH_CLIENT_SECRET"))


def _redirect_uri() -> str:
    return _env("OAUTH_REDIRECT_URI") or "https://cockpit.bethelightdecor.com/"


# ── HMAC signing (OAuth state + session token) ────────────────────────────────

def _sign(payload: str) -> str:
    key = _env("BTL_SESSION_KEY").encode() or b"dev-insecure-key"
    sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def _verify(token: str) -> str | None:
    try:
        payload, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    key = _env("BTL_SESSION_KEY").encode() or b"dev-insecure-key"
    expected = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return payload if hmac.compare_digest(sig, expected) else None


def make_state() -> str:
    """Signed, self-expiring CSRF state (survives the redirect statelessly)."""
    nonce = base64.urlsafe_b64encode(os.urandom(9)).decode()
    return _sign(f"{nonce}:{int(time.time())}")


def check_state(state: str, max_age: int = 600) -> bool:
    payload = _verify(state or "")
    if not payload or ":" not in payload:
        return False
    try:
        ts = int(payload.rsplit(":", 1)[1])
    except ValueError:
        return False
    return (time.time() - ts) <= max_age


def make_session_token(email: str) -> str:
    return _sign(f"{email}|{int(time.time()) + SESSION_TTL_SEC}")


def read_session_token(token: str) -> str | None:
    """Return the email if the session token is valid and unexpired."""
    payload = _verify(token or "")
    if not payload or "|" not in payload:
        return None
    email, _, exp = payload.rpartition("|")
    try:
        if int(exp) < time.time():
            return None
    except ValueError:
        return None
    return email


# ── encrypted per-member refresh-token store ──────────────────────────────────

def _store_path() -> Path:
    data_vol = Path("/data")
    base = data_vol if data_vol.is_dir() else (Path.home() / ".claude")
    return base / "gmail_tokens.json"


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(_env("BTL_TOKEN_ENC_KEY").encode())


def _load_store() -> dict:
    try:
        return json.loads(_store_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_refresh_token(email: str, refresh_token: str) -> None:
    store = _load_store()
    store[email.lower()] = _fernet().encrypt(refresh_token.encode()).decode()
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store), encoding="utf-8")


def get_refresh_token(email: str) -> str | None:
    enc = _load_store().get(email.lower())
    if not enc:
        return None
    try:
        return _fernet().decrypt(enc.encode()).decode()
    except Exception:  # noqa: BLE001 — bad/rotated key → treat as not-connected
        return None


def connected_members() -> list[str]:
    return sorted(_load_store().keys())


def is_connected(email: str) -> bool:
    return email.lower() in _load_store()


# ── OAuth flow ────────────────────────────────────────────────────────────────

def _flow(state: str | None = None):
    from google_auth_oauthlib.flow import Flow
    cfg = {
        "web": {
            "client_id": _env("GOOGLE_OAUTH_CLIENT_ID"),
            "client_secret": _env("GOOGLE_OAUTH_CLIENT_SECRET"),
            "auth_uri": _AUTH_URI,
            "token_uri": _TOKEN_URI,
            "redirect_uris": [_redirect_uri()],
        }
    }
    flow = Flow.from_client_config(cfg, scopes=SCOPES, state=state)
    flow.redirect_uri = _redirect_uri()
    # Disable PKCE: the sign-in link and the callback run statelessly (no shared
    # server session), so the one-time code_verifier can't survive the round-trip
    # and Google rejects the exchange with "Missing code verifier". We're a
    # confidential client (client_secret), so PKCE isn't needed.
    flow.autogenerate_code_verifier = False
    flow.code_verifier = None
    return flow


def auth_url() -> str:
    """The Google sign-in URL to send the member to."""
    flow = _flow(state=make_state())
    # No forced prompt: Google shows consent on the FIRST connect (returning a
    # refresh_token), then re-logins are silent. The callback handler covers the
    # rare "already-authorized-elsewhere, no refresh_token" case.
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
    )
    return url


def handle_callback(code: str, state: str) -> tuple[str | None, str | None]:
    """Exchange the code. Returns (email, error). Stores the refresh token."""
    import sys
    # Generous window: the state only guards against forged callbacks, and a
    # slow consent screen shouldn't read as "invalid". 1 hour is plenty.
    if not check_state(state, max_age=3600):
        print(f"[gmail_auth] callback: STATE CHECK FAILED (state={(state or '')[:24]}...)",
              file=sys.stderr, flush=True)
        return None, "Sign-in link expired — click Sign in with Google again."
    try:
        flow = _flow(state=state)
        flow.fetch_token(code=code)
        creds = flow.credentials
        email = _email_from_creds(creds)
        print(f"[gmail_auth] callback: token OK, email={email}, "
              f"has_refresh={bool(creds.refresh_token)}", file=sys.stderr, flush=True)
        if not email:
            return None, "Could not read your email from Google."
        if not email.lower().endswith("@" + ALLOWED_DOMAIN):
            return None, f"Only @{ALLOWED_DOMAIN} accounts can connect."
        if creds.refresh_token:
            save_refresh_token(email, creds.refresh_token)
        elif not is_connected(email):
            return None, ("Google didn't return a refresh token. Remove BTL Cockpit "
                          "from your Google account's connected apps, then sign in again.")
        return email, None
    except Exception as e:  # noqa: BLE001
        import traceback
        print("[gmail_auth] callback EXCEPTION:\n" + traceback.format_exc(),
              file=sys.stderr, flush=True)
        return None, f"Sign-in failed: {str(e)[:200]}"


def _email_from_creds(creds) -> str | None:
    # id_token is a JWT; the middle segment holds the claims. We received it
    # directly from Google's token endpoint over TLS, so decode without a
    # second network round-trip.
    tok = getattr(creds, "id_token", None)
    if tok:
        try:
            payload = tok.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            if claims.get("email"):
                return claims["email"]
        except Exception:  # noqa: BLE001
            pass
    # fallback: call userinfo
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()).get("email")
    except Exception:  # noqa: BLE001
        return None


# ── read-only Gmail fetch ─────────────────────────────────────────────────────

def _member_creds(email: str):
    """Refreshed Google credentials for a connected member, or None."""
    rt = get_refresh_token(email)
    if not rt:
        return None
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    creds = Credentials(
        token=None, refresh_token=rt,
        client_id=_env("GOOGLE_OAUTH_CLIENT_ID"),
        client_secret=_env("GOOGLE_OAUTH_CLIENT_SECRET"),
        token_uri=_TOKEN_URI, scopes=SCOPES,
    )
    creds.refresh(Request())
    return creds


def fetch_unread(email: str, max_results: int = 15) -> tuple[list[dict], str | None]:
    """Return (messages, error) for the member's unread inbox. Read-only."""
    if not get_refresh_token(email):
        return [], "not connected"
    try:
        from googleapiclient.discovery import build
        creds = _member_creds(email)
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        listing = service.users().messages().list(
            userId="me", q="is:unread in:inbox", maxResults=max_results).execute()
        out = []
        for m in listing.get("messages", []):
            md = service.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]).execute()
            headers = {h["name"]: h["value"]
                       for h in md.get("payload", {}).get("headers", [])}
            out.append({
                "from": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(no subject)"),
                "date": headers.get("Date", "")[:31],
                "snippet": md.get("snippet", "")[:200],
            })
        return out, None
    except Exception as e:  # noqa: BLE001
        return [], f"Gmail fetch failed: {str(e)[:140]}"


def unread_block(email: str) -> tuple[str | None, str | None]:
    """Formatted '=== GMAIL UNREAD ===' block for the inbox-digest prompt."""
    msgs, err = fetch_unread(email)
    if err == "not connected":
        return None, f"{email} has not connected their Gmail yet."
    if err:
        return None, err
    if not msgs:
        return f"=== {email} GMAIL — LIVE DATA ===\nNo unread messages in the inbox.\n", None
    lines = [f"=== {email} GMAIL UNREAD — LIVE DATA ({len(msgs)} messages) ==="]
    for m in msgs:
        lines.append(f"- From: {m['from']} | {m['date']}")
        lines.append(f"  Subject: {m['subject']}")
        if m["snippet"]:
            lines.append(f"  Preview: {m['snippet']}")
    return "\n".join(lines) + "\n", None


# ── read-only Calendar fetch ──────────────────────────────────────────────────

def fetch_today_events(email: str) -> tuple[list[dict], str | None]:
    """Return (events, error) for the member's own calendar today. Read-only.
    Each event: {'time': '9:00 AM' | 'all-day', 'label': summary}."""
    if not get_refresh_token(email):
        return [], "not connected"
    try:
        from googleapiclient.discovery import build
        creds = _member_creds(email)
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        now_local = datetime.now(BTL_TZ)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        res = service.events().list(
            calendarId="primary",
            timeMin=day_start.astimezone(timezone.utc).isoformat(),
            timeMax=day_end.astimezone(timezone.utc).isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=20,
        ).execute()

        out = []
        for e in res.get("items", []):
            start = e.get("start", {})
            if start.get("dateTime"):
                try:
                    t = datetime.fromisoformat(start["dateTime"]).astimezone(BTL_TZ)
                    label_time = t.strftime("%I:%M %p").lstrip("0")
                except ValueError:
                    label_time = ""
            else:
                label_time = "all-day"
            out.append({"time": label_time, "label": e.get("summary", "(no title)")})
        return out, None
    except Exception as e:  # noqa: BLE001
        return [], f"Calendar fetch failed: {str(e)[:140]}"
