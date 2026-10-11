"""Both public entrypoints surface actionable validation failures."""
import os
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

import pytest
from fastapi.testclient import TestClient
import gradio as gr
import app
import annotation_app
import web_shared


def test_space_entrypoint_serves_mobile_ui_api_and_gradio():
    with TestClient(app.app) as client:
        assert 'id="startBtn"' in client.get("/").text
        assert client.get("/health").json()["ok"]
        assert len(client.get("/api/geo").json()["geo"]) == 28
        response = client.get("/gradio/")
        assert response.status_code == 200 and "TriTowers" in response.text


@pytest.mark.parametrize("corners", ["a,b", "nan,0,0,100,100,100,100,0", "0,0,0,0,0,0,0,0"])
def test_bad_corners_produce_gradio_error(corners):
    with pytest.raises(gr.Error, match="Corners"):
        app.inspect_image("unused", corners)


def test_nonimage_produces_useful_error(tmp_path):
    path = tmp_path / "fake.jpg"; path.write_bytes(b"not an image")
    with pytest.raises(gr.Error, match="Could not read that image"):
        app.inspect_image(str(path), "")


def test_start_and_draw_without_selection_are_validation_errors():
    with pytest.raises(gr.Error, match="waste"):
        app.start(" ".join(["?"] * 28), None, 23)
    session = app.ui.new_session(" ".join(["6"] + ["--"] * 27), "5", 2)
    with pytest.raises(gr.Error, match="rank"):
        app.draw(session, None)
    assert session.game.stock_remaining == 2 and not session.history


def test_deep_annotation_json_is_rejected():
    result, message = annotation_app.validate_annotation("[" * 2000 + "]" * 2000)
    assert result is None and "nesting" in message


def test_large_annotation_json_is_rejected():
    result, message = annotation_app.validate_annotation(" " * (2 * 1024 * 1024 + 1))
    assert result is None and "2 MB" in message


def test_gradio_known_deal_uses_verified_shared_solver():
    message, steps = app.complete_deal(" ".join(["6"] + ["--"] * 27), "5", "")
    assert "verified by replay" in message and "position 1" in steps
