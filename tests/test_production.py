"""Lightweight production configuration, health, and safe error responses."""

import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

import app as application


def test_health_is_fast_side_effect_free_json(monkeypatch):
    def unexpected_work(*_args, **_kwargs):
        raise AssertionError("Health checks must not load catalogs or calculate geometry")

    monkeypatch.setattr(application, "load_materials", unexpected_work)
    monkeypatch.setattr(application.crystal, "generate_supercell", unexpected_work)
    response = application.app.test_client().get("/health")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {"status": "ok"}


def test_unknown_page_uses_shared_safe_404_template():
    response = application.app.test_client().get("/missing-page")
    assert response.status_code == 404
    html = response.get_data(as_text=True)
    assert "Page not found" in html
    assert '<a href="/">Return to Explorer</a>' in html
    assert 'aria-label="Primary navigation"' in html
    assert "/static/css/style.css" in html
    assert 'class="app-booting"' not in html


def test_production_exception_uses_safe_500_without_public_crash_route(monkeypatch):
    private_details = "private exception details that must never appear in HTML"

    def failed_page():
        raise RuntimeError(private_details)

    monkeypatch.setitem(application.app.config, "TESTING", False)
    monkeypatch.setitem(application.app.config, "PROPAGATE_EXCEPTIONS", False)
    monkeypatch.setitem(application.app.view_functions, "about", failed_page)
    response = application.app.test_client().get("/about")
    assert response.status_code == 500
    html = response.get_data(as_text=True)
    assert "Something went wrong" in html
    assert '<a href="/">Return to Explorer</a>' in html
    assert 'aria-label="Primary navigation"' in html
    assert private_details not in html
    assert "Traceback" not in html
    assert "Werkzeug Debugger" not in html
    assert not any("test-error" in rule.rule for rule in application.app.url_map.iter_rules())


def test_import_is_debug_off_even_when_local_debug_is_requested():
    environment = {**os.environ, "CRYSTAL_DEBUG": "1", "FLASK_DEBUG": "1"}
    result = subprocess.run(
        [sys.executable, "-c", "import app; assert app.app.debug is False"],
        cwd=Path(application.__file__).resolve().parent,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(("debug_value", "expected"), [(None, False), ("1", True)])
def test_local_launch_requires_explicit_debug_opt_in(monkeypatch, debug_value, expected):
    calls = []
    monkeypatch.setattr(application.Flask, "run", lambda _app, **options: calls.append(options))
    if debug_value is None:
        monkeypatch.delenv("CRYSTAL_DEBUG", raising=False)
    else:
        monkeypatch.setenv("CRYSTAL_DEBUG", debug_value)
    runpy.run_path(application.__file__, run_name="__main__")
    assert calls == [{"debug": expected}]
