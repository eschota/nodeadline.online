from __future__ import annotations

import re
import urllib.parse
import urllib.request


def build_google_auth_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    })
    return f"https://accounts.google.com/o/oauth2/v2/auth?{q}"


def exchange_code(*, code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        import json
        return json.loads(resp.read().decode())


def fetch_userinfo(access_token: str) -> dict:
    req = urllib.request.Request("https://www.googleapis.com/oauth2/v3/userinfo")
    req.add_header("Authorization", f"Bearer {access_token}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        import json
        return json.loads(resp.read().decode())


def normalize_username(email: str) -> str:
    local = (email or "user").split("@")[0].lower()
    local = re.sub(r"[^a-z0-9._-]+", "-", local).strip("-") or "user"
    return local[:48]
