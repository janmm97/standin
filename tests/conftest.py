import pytest


@pytest.fixture(autouse=True)
def _no_real_image_provider(monkeypatch):
    """Auto-detection would find a real Codex login or API key on a dev machine; tests pick explicitly."""
    monkeypatch.setenv("STANDIN_IMAGES", "higgsfield")
