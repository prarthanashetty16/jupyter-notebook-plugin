"""Trivial smoke test to verify pytest setup."""


def test_import():
    """Test that nexus package imports without error."""
    import nexus
    assert nexus.__version__ is not None


def test_true():
    """Trivial sanity test."""
    assert True
