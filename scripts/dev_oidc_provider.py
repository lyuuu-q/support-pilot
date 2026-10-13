"""Local OIDC provider for manual demos and browser end-to-end tests.

This is deliberately a small, in-memory stand-in: it exists so the authorization
code flow can be exercised end to end without an external identity provider. It
must never be used for anything but local demonstration.
"""

import base64
import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

ISSUER = os.getenv("DEV_OIDC_ISSUER", "http://127.0.0.1:18002")
CLIENT_ID = os.getenv("DEV_OIDC_CLIENT_ID", "support-pilot-console")
DEMO_PASSWORD = os.getenv("DEV_OIDC_PASSWORD", "SupportPilotDemo!2026")
ALLOWED_EMAILS = {
    email.strip().casefold()
    for email in os.getenv(
        "DEV_OIDC_EMAILS",
        "alpha.admin@example.com,beta.developer@example.com,support.agent@example.com",
    ).split(",")
    if email.strip()
}

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
KEY_ID = "dev-key-1"
CODES: dict[str, dict[str, str]] = {}

app = FastAPI(title="SupportPilot development OIDC provider")


def _b64(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _challenge(verifier: str) -> str:
    digest = sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@app.get("/.well-known/openid-configuration")
def discovery() -> dict[str, Any]:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/jwks.json",
        "id_token_signing_alg_values_supported": ["RS256"],
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
    }


@app.get("/jwks.json")
def jwks() -> dict[str, Any]:
    numbers = KEY.public_key().public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": KEY_ID,
                "use": "sig",
                "alg": "RS256",
                "n": _b64(numbers.n),
                "e": _b64(numbers.e),
            }
        ]
    }


@app.get("/authorize", response_class=HTMLResponse)
def authorize(
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    nonce: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
    scope: str = "",
) -> HTMLResponse:
    if client_id != CLIENT_ID:
        raise HTTPException(status_code=400, detail="unknown client_id")
    if code_challenge_method != "S256" or not code_challenge:
        raise HTTPException(status_code=400, detail="PKCE S256 is required")
    options = "".join(
        f'<option value="{email}">{email}</option>' for email in sorted(ALLOWED_EMAILS)
    )
    return HTMLResponse(
        f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>SupportPilot 开发用身份提供方</title></head>
<body style="font-family: sans-serif; max-width: 420px; margin: 60px auto;">
<h1>开发用身份提供方</h1>
<p>仅用于本地演示与自动化测试，不是真实身份系统。</p>
<form method="post" action="/approve">
  <input type="hidden" name="redirect_uri" value="{redirect_uri}">
  <input type="hidden" name="state" value="{state}">
  <input type="hidden" name="nonce" value="{nonce}">
  <input type="hidden" name="code_challenge" value="{code_challenge}">
  <p><label for="email">邮箱</label><br>
  <input id="email" name="email" type="email" list="accounts" required
         value="alpha.admin@example.com"></p>
  <datalist id="accounts">{options}</datalist>
  <p><label for="password">密码</label><br>
  <input id="password" name="password" type="password" required></p>
  <p><button type="submit">登录</button></p>
</form>
<p style="color:#666">允许的合成账号：{", ".join(sorted(ALLOWED_EMAILS))}</p>
</body></html>"""
    )


@app.post("/approve")
def approve(
    email: str = Form(...),
    password: str = Form(...),
    redirect_uri: str = Form(...),
    state: str = Form(""),
    nonce: str = Form(""),
    code_challenge: str = Form(...),
) -> RedirectResponse:
    normalized = email.strip().casefold()
    if normalized not in ALLOWED_EMAILS or password != DEMO_PASSWORD:
        raise HTTPException(status_code=401, detail="unknown synthetic account or wrong password")
    code = token_urlsafe(24)
    CODES[code] = {
        "email": normalized,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "redirect_uri": redirect_uri,
    }
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{separator}code={code}&state={state}", status_code=302)


@app.post("/token")
async def token(request: Request) -> dict[str, Any]:
    form = await request.form()
    code = str(form.get("code", ""))
    payload = CODES.pop(code, None)
    if payload is None:
        raise HTTPException(status_code=400, detail="unknown or already used code")
    verifier = str(form.get("code_verifier", ""))
    if not verifier or _challenge(verifier) != payload["code_challenge"]:
        raise HTTPException(status_code=400, detail="PKCE verification failed")
    if str(form.get("client_id", "")) != CLIENT_ID:
        raise HTTPException(status_code=400, detail="unknown client_id")
    if str(form.get("redirect_uri", "")) != payload["redirect_uri"]:
        raise HTTPException(status_code=400, detail="redirect_uri mismatch")
    now = datetime.now(UTC)
    id_token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": f"dev-{payload['email']}",
            "email": payload["email"],
            "email_verified": True,
            "name": payload["email"].split("@")[0],
            "iat": now,
            "exp": now + timedelta(minutes=10),
            "nonce": payload["nonce"],
        },
        KEY,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )
    return {
        "access_token": token_urlsafe(24),
        "token_type": "Bearer",
        "expires_in": 600,
        "id_token": id_token,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("DEV_OIDC_PORT", "18002")))
