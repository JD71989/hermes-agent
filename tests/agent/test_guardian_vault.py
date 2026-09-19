from __future__ import annotations

import agent.guardian.vault as vault


def test_vault_encrypts_and_applies_withdrawal_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(vault, "_db_path", lambda: tmp_path / "vault.db")
    vault._ACTIVE.clear()

    created = vault.setup("correct horse battery staple", authorize_runtime=False)
    token = created["token"]
    item = vault.save_credential(
        token,
        credential_id=None,
        label="Sandbox Signup",
        kind="login",
        environment="sandbox",
        username="user@example.test",
        secret="super-secret",
        allowed_consumers=["guardian"],
        approval="sandbox_auto",
    )

    listed = vault.list_credentials(token)
    assert len(listed) == 1
    assert "secret" not in listed[0]
    withdrawn = vault.withdraw(
        token,
        item["id"],
        consumer="guardian",
        purpose="signup form",
        environment="sandbox",
        ttl_seconds=60,
    )
    assert withdrawn["secret"] == "super-secret"
    assert withdrawn["username"] == "user@example.test"

    prod = vault.save_credential(
        token,
        credential_id=None,
        label="Production Master",
        kind="master_key",
        environment="production",
        username="root",
        secret="prod-secret",
        allowed_consumers=["guardian"],
        approval="master",
    )
    standard = vault.unlock("correct horse battery staple", elevated=False)
    try:
        vault.withdraw(
            standard["token"],
            prod["id"],
            consumer="guardian",
            purpose="protected operation",
            environment="production",
            ttl_seconds=60,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("production/master credential must require elevated session")

    elevated = vault.unlock("correct horse battery staple", elevated=True)
    out = vault.withdraw(
        elevated["token"],
        prod["id"],
        consumer="guardian",
        purpose="operator-authorized protected operation",
        environment="production",
        ttl_seconds=60,
    )
    assert out["secret"] == "prod-secret"
    vault.lock()
