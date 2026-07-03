"""Unit tests for webinterface/app.py."""

from _pytest.monkeypatch import MonkeyPatch

from tests.module_factory import ModuleFactory


def test_favicon_returns_no_content(monkeypatch: MonkeyPatch) -> None:
    """Verify favicon requests do not create browser 404 console errors.

    Parameters:
        monkeypatch: Pytest fixture used to isolate command-line arguments.

    Return:
        None.
    """
    module_factory = ModuleFactory()
    _ = module_factory
    monkeypatch.setattr("sys.argv", ["./slips.py"])
    from webinterface.app import app

    client = app.test_client()

    response = client.get("/favicon.ico")

    assert response.status_code == 204
    assert response.data == b""
