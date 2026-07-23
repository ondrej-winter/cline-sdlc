"""Package metadata tests."""

from cline_sdlc import __version__


def test_package_exposes_version() -> None:
    """The installed package exposes its distribution version."""
    assert __version__ == "0.1.0"
