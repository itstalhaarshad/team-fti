"""Email signup/login via Firebase Authentication (Identity Toolkit REST API).

Pure REST (no heavy SDK). Reads FIREBASE_WEB_API_KEY. If that env var is unset, auth is
disabled and the app runs in single-user local mode (no sign-in gate).
"""
from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

load_dotenv()

_BASE = "https://identitytoolkit.googleapis.com/v1/accounts"
_TOKEN = "https://securetoken.googleapis.com/v1/token"

_FRIENDLY = {
    "EMAIL_EXISTS": "That email is already registered — try signing in instead.",
    "INVALID_LOGIN_CREDENTIALS": "Incorrect email or password.",
    "EMAIL_NOT_FOUND": "No account found with that email.",
    "INVALID_PASSWORD": "Incorrect password.",
    "INVALID_EMAIL": "That doesn't look like a valid email address.",
    "WEAK_PASSWORD": "Password must be at least 6 characters.",
    "MISSING_PASSWORD": "Please enter a password.",
    "USER_DISABLED": "This account has been disabled.",
}


class AuthError(Exception):
    pass


def auth_enabled() -> bool:
    return bool(os.environ.get("FIREBASE_WEB_API_KEY", "").strip())


def _key() -> str:
    k = os.environ.get("FIREBASE_WEB_API_KEY", "").strip()
    if not k:
        raise AuthError("FIREBASE_WEB_API_KEY is not set.")
    return k


def _friendly(msg: str) -> str:
    for code, text in _FRIENDLY.items():
        if msg.startswith(code):
            return text
    return msg.replace("_", " ").capitalize()


def _post(method: str, payload: dict) -> dict:
    try:
        r = requests.post(f"{_BASE}:{method}?key={_key()}", json=payload, timeout=20)
    except requests.RequestException as e:
        raise AuthError(f"Network error reaching Firebase: {e}")
    data = r.json() if r.content else {}
    if r.status_code != 200:
        raise AuthError(_friendly(data.get("error", {}).get("message", "Authentication failed.")))
    return data


def _session(d: dict) -> dict:
    return {
        "uid": d["localId"],
        "email": d.get("email", ""),
        "id_token": d.get("idToken", ""),
        "refresh_token": d.get("refreshToken", ""),
    }


def sign_up(email: str, password: str) -> dict:
    """Create a new account and return a session dict (uid, email, tokens)."""
    return _session(_post("signUp", {"email": email, "password": password, "returnSecureToken": True}))


def sign_in(email: str, password: str) -> dict:
    """Sign in an existing account and return a session dict."""
    return _session(_post("signInWithPassword",
                          {"email": email, "password": password, "returnSecureToken": True}))
