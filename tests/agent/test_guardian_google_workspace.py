from agent.guardian.google_workspace import ADMIN_SCOPE, build_user_payload, capabilities


def test_workspace_user_payload():
    body = build_user_payload(
        primary_email="agent01@example.com",
        given_name="Agent",
        family_name="One",
        password="StrongPass123!",
    )
    assert body["primaryEmail"] == "agent01@example.com"
    assert body["name"]["givenName"] == "Agent"
    assert body["suspended"] is False


def test_workspace_capabilities_are_controlled():
    info = capabilities()
    assert info["scope"] == ADMIN_SCOPE
    assert info["consumer_gmail_creation"] is False
    assert info["phone_verification_bypass"] is False
    assert info["bulk_unmanaged_accounts"] is False
