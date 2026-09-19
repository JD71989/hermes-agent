from agent.guardian.wallets import _derive_wallet


MNEMONIC = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"


def test_known_evm_bip44_vector():
    address, path, private_key = _derive_wallet(MNEMONIC, "evm")
    assert address == "0x9858EfFD232B4033E47d90003D41EC34EcaEda94"
    assert path == "m/44'/60'/0'/0/0"
    assert len(private_key) == 64


def test_solana_vector_shape():
    address, path, private_key = _derive_wallet(MNEMONIC, "solana")
    assert path == "m/44'/501'/0'/0'"
    assert len(address) >= 32
    assert len(private_key) == 64
