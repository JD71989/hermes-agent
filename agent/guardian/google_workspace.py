from __future__ import annotations

import json
import re
from typing import Any

from . import vault

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ADMIN_SCOPE = "https://www.googleapis.com/auth/admin.directory.user"


def build_user_payload(*, primary_email: str, given_name: str, family_name: str,
                       password: str, suspended: bool = False) -> dict[str, Any]:
    primary_email = primary_email.strip().lower()
    given_name = given_name.strip()
    family_name = family_name.strip()
    if not EMAIL_RE.match(primary_email):
        raise ValueError("Invalid Workspace primary email.")
    if not given_name or not family_name:
        raise ValueError("Given and family names are required.")
    if len(password) < 8:
        raise ValueError("Workspace password must be at least 8 characters.")
    return {
        "primaryEmail": primary_email,
        "name": {"givenName": given_name, "familyName": family_name},
        "password": password,
        "suspended": bool(suspended),
        "changePasswordAtNextLogin": False,
    }


def provision_user(
    token: str,
    *,
    service_credential_id: str,
    primary_email: str,
    given_name: str,
    family_name: str,
    admin_email: str = "",
    password: str = "",
    customer_id: str = "my_customer",
) -> dict[str, Any]:
    """Create one admin-controlled Google Workspace user."""
    if not service_credential_id:
        raise ValueError("A Vault service-account credential is required.")
    credential = vault.withdraw(
        token,
        service_credential_id,
        consumer="guardian",
        purpose="Google Workspace user provisioning",
        environment="production",
        ttl_seconds=300,
    )
    try:
        info = json.loads(credential["secret"])
    except Exception as exc:
        raise ValueError("Vault credential does not contain valid service-account JSON.") from exc

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Google Workspace dependencies are not installed. Use the existing google Hermes extra.") from exc

    if not admin_email or "@" not in admin_email:
        raise ValueError("A Workspace admin email is required for service-account delegation.")
    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=[ADMIN_SCOPE],
    ).with_subject(admin_email.strip().lower())
    directory = build("admin", "directory_v1", credentials=credentials, cache_discovery=False)
    body = build_user_payload(
        primary_email=primary_email,
        given_name=given_name,
        family_name=family_name,
        password=password,
    )
    result = directory.users().insert(customer=customer_id, body=body).execute()
    verified = False
    verification_error = ""
    try:
        verification = directory.users().get(
            customer=customer_id,
            userKey=result.get("primaryEmail", primary_email),
        ).execute()
        verified = (
            verification.get("id") == result.get("id")
            and verification.get("primaryEmail", "").lower()
            == result.get("primaryEmail", primary_email).lower()
        )
    except Exception as exc:
        verification_error = str(exc)
    vault._audit(
        "google_workspace_create_user",
        result="success",
        credential_id=service_credential_id,
        label=primary_email,
        consumer="guardian",
        purpose="Google Workspace user provisioning",
        reason="admin.directory.user",
    )
    return {
        "id": result.get("id", ""),
        "primary_email": result.get("primaryEmail", primary_email),
        "status": "active" if not result.get("suspended") else "suspended",
        "customer_id": customer_id,
        "verified": verified,
        "verification_error": verification_error,
    }


def capabilities() -> dict[str, Any]:
    return {
        "provider": "google_workspace",
        "supported": True,
        "mode": "domain_admin",
        "scope": ADMIN_SCOPE,
        "consumer_gmail_creation": False,
        "anti_detection": False,
        "phone_verification_bypass": False,
        "bulk_unmanaged_accounts": False,
        "note": "Creates admin-controlled users in a Google Workspace domain you control.",
    }
