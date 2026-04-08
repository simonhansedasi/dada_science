"""
hold.py — Sno-Isle hold placement

Handles login, account resolution, and hold submission against the
BiblioCommons gateway API.

Credentials are read from environment variables:
    SNOISLE_CARD  — library card number
    SNOISLE_PIN   — PIN / password

These can be set in a .env file in the project directory (never commit it).
"""

import base64
import os
import re

import requests

LOGIN_URL   = "https://sno-isle.bibliocommons.com/user/login"
LOGIN_JSON  = "https://sno-isle.bibliocommons.com/user/login.json"
ME_URL      = "https://gateway.bibliocommons.com/v2/libraries/sno-isle/users/me"
HOLDS_URL   = "https://gateway.bibliocommons.com/v2/libraries/sno-isle/holds"
BRANCHES_URL     = "https://gateway.bibliocommons.com/v2/libraries/sno-isle/branches"
AVAILABILITY_URL = "https://gateway.bibliocommons.com/v2/libraries/sno-isle/bibs/{}/availability"


def _make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0",
        "Accept": "application/json",
    })
    return s


def _load_credentials():
    """Return (card, pin) from environment variables, or (None, None)."""
    # Support a simple .env file in the project directory
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

    card = os.environ.get("SNOISLE_CARD")
    pin  = os.environ.get("SNOISLE_PIN")
    return card, pin


def login(card, pin):
    """
    Log in with a library card number and PIN.
    Follows the full SSO redirect chain so the gateway API session is
    properly activated for authenticated calls (holds, checkouts, etc.).
    Returns a requests.Session on success, raises RuntimeError on failure.
    """
    session = _make_session()

    # GET the login page to initialise the session cookie (required for CSRF)
    session.get(LOGIN_URL, timeout=15)

    resp = session.post(
        LOGIN_JSON,
        json={"name": card, "user_pin": pin},
        headers={"Content-Type": "application/json",
                 "Referer": LOGIN_URL},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if not data.get("logged_in"):
        msgs = [m.get("key", "") for m in data.get("messages", [])]
        raise RuntimeError("Login failed: " + (msgs[0] if msgs else "unknown error"))

    # Follow the SSO redirect chain, then re-establish the session on the
    # catalog side. Without this two-step, the gateway API returns empty data.
    sso_url = data.get("redirect", "")
    if sso_url:
        session.get(sso_url, timeout=15, allow_redirects=True)
        # The SSO chain lands on www.sno-isle.org, leaving the bibliocommons
        # session un-warmed. Re-visit the catalog to activate the gateway session.
        session.get(LOGIN_URL.replace("/user/login", ""), timeout=15)

    return session


def get_account_id(session):
    """
    Return the (accountId, page_text) for the logged-in user.
    The accountId is the BiblioCommons internal account ID embedded in
    the holds page JSON state — NOT the patron number in the session cookie.
    Raises RuntimeError if it cannot be found.
    """
    resp = session.get("https://sno-isle.bibliocommons.com/holds", timeout=15)
    match = re.search(r'"accounts"\s*:\s*\{"(\d+)"', resp.text)
    if match:
        return match.group(1), resp.text

    raise RuntimeError(
        "Could not determine accountId. Are you logged in?\n"
        "Check that SNOISLE_CARD and SNOISLE_PIN are correct in .env"
    )


def get_availability(metadata_id):
    """
    Return a list of per-copy dicts with keys:
        branch_name, branch_code, collection, call_number, status, library_status
    """
    s = _make_session()
    s.headers.update({
        "Origin":  "https://sno-isle.bibliocommons.com",
        "Referer": "https://sno-isle.bibliocommons.com/",
    })
    resp = s.get(AVAILABILITY_URL.format(metadata_id), timeout=15)
    resp.raise_for_status()
    data = resp.json()

    copies = []
    for item in data.get("entities", {}).get("bibItems", {}).values():
        avail = item.get("availability", {})
        branch = item.get("branch", {})
        copies.append({
            "branch_name":    branch.get("name", "Unknown"),
            "branch_code":    branch.get("code", ""),
            "collection":     item.get("collection", ""),
            "call_number":    item.get("callNumber", ""),
            "status":         avail.get("status", ""),
            "library_status": avail.get("libraryStatus", ""),
        })
    copies.sort(key=lambda c: c["branch_name"])
    return copies


def get_branches():
    """Return a list of (branch_id, branch_name) sorted by name."""
    s = _make_session()
    resp = s.get(BRANCHES_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    branches = data.get("entities", {}).get("branches", {})
    return sorted(
        [(code, info["name"]) for code, info in branches.items()],
        key=lambda x: x[1],
    )


def place_hold(session, account_id, metadata_id, pickup_branch_id):
    """
    Place a hold on a bib item.

    Returns the API response dict on success.
    Raises RuntimeError with the API error message on failure.
    """
    payload = {
        "accountId":             int(account_id),
        "materialType":          "PHYSICAL",
        "metadataId":            metadata_id,
        "enableSingleClickHolds": True,
        "materialParams": {
            "branchId":            str(pickup_branch_id),
            "expiryDate":          None,
            "errorMessageLocale":  "en-US",
        },
    }
    token = next((c.value for c in session.cookies if c.name == "bc_access_token"), None)
    headers = {
        "Content-Type": "application/json",
        "Origin":  "https://sno-isle.bibliocommons.com",
        "Referer": "https://sno-isle.bibliocommons.com/holds",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = session.post(HOLDS_URL, json=payload, headers=headers, timeout=15)

    if resp.status_code in (200, 201):
        return resp.json()

    try:
        err = resp.json().get("error", {})
        msg = err.get("message") or str(err)
    except Exception:
        msg = resp.text[:500]
    raise RuntimeError(f"Hold failed ({resp.status_code}): {msg}")


GATEWAY = "https://gateway.bibliocommons.com/v2/libraries/sno-isle"
_GATEWAY_HEADERS = {
    "Origin":  "https://sno-isle.bibliocommons.com",
    "Referer": "https://sno-isle.bibliocommons.com/holds",
}


def _gateway_get(session, path, attempts=5):
    """
    GET a gateway API path, retrying on different servers if needed.
    Some NERF servers don't have the session data replicated yet; dropping
    the NERF_SRV cookie forces the load balancer to pick a different one.
    """
    for i in range(attempts):
        resp = session.get(
            f"{GATEWAY}/{path}", headers=_GATEWAY_HEADERS, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        # If the response has real content, return it
        borrowing = data.get("borrowing", {})
        has_data = any(
            borrowing.get(k, {}).get("pagination", {}).get("count", 0) > 0
            for k in ("holds", "checkouts")
        )
        if has_data or i == attempts - 1:
            return data
        # Clear only the server-pin cookie so the load balancer picks a
        # different backend on the next attempt.
        session.cookies.set("NERF_SRV", "", domain=".bibliocommons.com")
    return data


def get_holds(session, account_id):
    """Return list of hold dicts for the logged-in account."""
    data = _gateway_get(session, f"holds?accountId={account_id}&limit=100")
    hold_ids = data.get("borrowing", {}).get("holds", {}).get("items", [])
    holds_map = data.get("entities", {}).get("holds", {})
    bibs_map  = data.get("entities", {}).get("bibs", {})

    result = []
    for hid in hold_ids:
        hold = holds_map.get(hid, {})
        bib  = bibs_map.get(hold.get("metadataId", ""), {})
        info = bib.get("briefInfo", {})
        result.append({
            "title":          info.get("title", "Unknown"),
            "author":         (info.get("authors") or [""])[0],
            "status":         hold.get("status", ""),
            "position":       hold.get("holdsPosition"),
            "pickup_by":      hold.get("pickupByDate"),
            "pickup_branch":  (hold.get("pickupLocation") or {}).get("name", ""),
            "expiry":         hold.get("expiryDate"),
            "metadata_id":    hold.get("metadataId", ""),
        })
    return result


def get_checkouts(session, account_id):
    """Return list of currently checked-out book dicts."""
    data = _gateway_get(session, f"checkouts?accountId={account_id}&limit=100")
    checkout_ids = data.get("borrowing", {}).get("checkouts", {}).get("items", [])
    checkouts_map = data.get("entities", {}).get("checkouts", {})
    bibs_map      = data.get("entities", {}).get("bibs", {})

    result = []
    for cid in checkout_ids:
        checkout = checkouts_map.get(cid, {})
        bib      = bibs_map.get(checkout.get("metadataId", ""), {})
        info     = bib.get("briefInfo", {})
        result.append({
            "title":       info.get("title", "Unknown"),
            "author":      (info.get("authors") or [""])[0],
            "due_date":    checkout.get("dueDate", ""),
            "overdue":     checkout.get("overdue", False),
            "renewable":   checkout.get("canRenew", False),
            "metadata_id": checkout.get("metadataId", ""),
        })
    return result


def hold_book(metadata_id, pickup_branch_id, card=None, pin=None):
    """
    High-level helper: load credentials, log in, get accountId, place hold.
    Returns the API response dict.
    """
    if not card or not pin:
        env_card, env_pin = _load_credentials()
        card = card or env_card
        pin  = pin  or env_pin

    if not card or not pin:
        raise RuntimeError(
            "No credentials found.\n"
            "Set SNOISLE_CARD and SNOISLE_PIN environment variables, "
            "or add them to a .env file in the library_recommender directory."
        )

    session    = login(card, pin)
    account_id, _ = get_account_id(session)
    return place_hold(session, account_id, metadata_id, pickup_branch_id)
