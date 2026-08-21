# src/contacts.py
import json, difflib, re, os
import dns.resolver

# Resolve relative to this file, not the process's cwd — avoids the same class of
# bug as the path-resolution issue in main.py (behavior silently depending on
# where you happened to launch the script from).
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CONTACTS_PATH = os.path.join(_DATA_DIR, "contacts.json")


def load_contacts() -> dict:
    try:
        with open(CONTACTS_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_contact(name: str, email: str) -> None:
    """Was imported by main.py but never defined — this was a hard ImportError
    waiting to happen. Now it actually exists."""
    os.makedirs(_DATA_DIR, exist_ok=True)
    contacts = load_contacts()
    contacts[name.strip().lower()] = email.strip()
    with open(CONTACTS_PATH, "w") as f:
        json.dump(contacts, f, indent=2)


def _extract_email(value) -> str | None:
    """Your existing contacts.json has some entries stored as {'email': '...'}
    instead of a plain string (likely from an earlier version of this code, or
    manual editing) — this is what actually crashed send_email, since a dict got
    passed straight through as the recipient. Normalize both shapes here, once,
    so nothing downstream ever has to guess again."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("email")
    return None


def resolve_contact(name: str) -> list[tuple[str, str]]:
    """Returns [(name, email), ...] candidates for a spoken/typed name. Always
    returns plain string emails, regardless of how they're stored on disk."""
    contacts = load_contacts()
    matches = difflib.get_close_matches(name.strip().lower(), contacts.keys(), n=3, cutoff=0.6)
    results = []
    for m in matches:
        email = _extract_email(contacts[m])
        if email:
            results.append((m, email))
    return results


def is_valid_email_format(email: str) -> bool:
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()) is not None


def domain_can_receive_mail(email: str) -> bool:
    """Cheap sanity check: does the domain even have mail servers? Catches typos like
    'gmial.com' before you waste a send attempt on an address that can never work."""
    domain = email.split("@")[-1]
    try:
        return len(dns.resolver.resolve(domain, "MX")) > 0
    except Exception:
        return False


def get_email_by_name(name: str) -> str | None:
    """Resolve a contact name to an email address."""
    contacts = load_contacts()
    email = contacts.get(name.strip().lower())
    if email:
        return _extract_email(email)
    candidates = resolve_contact(name)
    if candidates:
        return candidates[0][1]
    return None