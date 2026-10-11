"""Full-grid drafts carry their stock through both public app adapters."""
from types import SimpleNamespace
import random

from PIL import Image
from fastapi.testclient import TestClient
import pytest

import solver
import web_core
import web_app
import web_shared


def draft_fixture():
    deck = [rank for rank in solver.RANKS for _ in range(4)]
    random.Random(3).shuffle(deck)
    stock = deck[29:] + ["*"]
    cards = {f"tableau-{p:02d}": {"state": "face_up", "rank": rank}
             for p, rank in enumerate(deck[:28], 1)}
    cards["waste"] = {"state": "face_up", "rank": deck[28]}
    cards.update({f"stock-{p:02d}": {"state": "face_up", "rank": rank}
                  for p, rank in enumerate(stock, 1)})
    return SimpleNamespace(draft={"cards": cards, "photo_kind": "full_deal", "stock": stock,
                           "registration": {"trusted": True}, "needs_human_review": []},
                           overlay=Image.new("RGB", (240, 180), "white"),
                           rectified=Image.new("RGB", (240, 180), "white"))


def test_grid_stock_is_identical_in_http_browser_and_exact_solver(monkeypatch):
    from tritowers_vision import intake
    draft = draft_fixture()
    monkeypatch.setattr(intake, "read_photo", lambda *args: draft)
    browser = web_core.api_photo(b"reader fixture")
    with TestClient(web_app.app) as client:
        http = client.post("/api/photo", files={"file": ("grid.jpg", b"reader fixture", "image/jpeg")}).json()
    assert http == browser
    assert http["mode"] == "full_deal" and http["trusted"]
    assert http["stock"] == draft.draft["stock"]
    assert http["stock_count"] == 24 and http["joker"] is True
    assert http["draw_direction"] == "right_to_left"
    solved = web_shared.solve_deal({"board": " ".join(http["board"]), "waste": http["waste"],
                                    "stock": http["stock"], "stock_count": http["stock_count"]})
    assert solved["status"] == "solved" and solved["frames"][-1]["remaining"] == 0


def test_unknown_grid_stock_is_preserved_for_review_and_cannot_solve(monkeypatch):
    from tritowers_vision import intake
    draft = draft_fixture()
    draft.draft["stock"][0] = "?"
    draft.draft["cards"]["stock-01"]["rank"] = None
    draft.draft["needs_human_review"] = ["tableau-03", "waste", "stock-01", "stock-23"]
    monkeypatch.setattr(intake, "read_photo", lambda *args: draft)
    response = web_core.api_photo(b"reader fixture")
    assert response["review"] == ["3", "waste", "stock-1", "stock-23"]
    assert response["stock"][0] == "?" and response["stock"][-1] == "*"
    result = web_shared.solve_deal({"board": " ".join(response["board"]), "waste": response["waste"],
                                    "stock": response["stock"], "stock_count": 24})
    assert result["status"] == "incomplete" and "stock card 1" in result["message"]
    assert "steps" not in result


def test_gradio_grid_draft_includes_editable_known_stock(monkeypatch):
    import app
    draft = draft_fixture()
    monkeypatch.setattr(app, "read_photo", lambda *args: draft)
    response = app.inspect_image("fixture.jpg", "")
    assert response[4].split() == [draft.draft["cards"][f"tableau-{i:02d}"]["rank"] for i in range(1, 29)]
    assert response[7].split() == draft.draft["stock"]
    assert "Known deal" in response[6] and "right to left" in response[6]
    assert len(app.inspect_image(None, "")) == len(response)


def test_decode_failure_remains_actionable():
    response = web_core.api_photo(b"not a photo")
    assert response["ok"] is False and "Could not read" in response["message"]
