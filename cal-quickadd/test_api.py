#!/usr/bin/env python3
"""Test FastAPI endpoints, request/response schemas, and edge cases.

Mocks the calendar API (requires OAuth) but hits Gemini for real parsing.
"""

import os
import sys
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

from app.main import app


@pytest.fixture
def mock_calendar():
    """Mock calendar_api.create_event so we don't need OAuth."""
    fake_event = {
        "id": "test123",
        "title": "mocked",
        "link": "https://calendar.google.com/event?id=test123",
        "start": {"dateTime": "2026-04-09T16:45:00-06:00"},
        "end": {"dateTime": "2026-04-09T17:45:00-06:00"},
    }
    with patch("app.main.calendar_api.create_event", return_value=fake_event) as mock:
        yield mock


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- Health endpoint ---

@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "timezone" in data
    assert "family_members" in data
    assert isinstance(data["family_members"], list)


# --- POST /add schema validation ---

@pytest.mark.asyncio
async def test_add_empty_text(client):
    resp = await client.post("/add", json={"text": ""})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_add_whitespace_only(client):
    resp = await client.post("/add", json={"text": "   "})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_add_missing_text(client):
    resp = await client.post("/add", json={})
    assert resp.status_code == 422  # Pydantic validation


@pytest.mark.asyncio
async def test_add_wrong_content_type(client):
    resp = await client.post("/add", content="not json", headers={"content-type": "text/plain"})
    assert resp.status_code == 422


# --- Successful parse + mock calendar create ---

@pytest.mark.asyncio
async def test_add_high_confidence(client, mock_calendar):
    resp = await client.post("/add", json={"text": "jonnie pta thursday 445pm"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "created"
    assert data["event"] is not None
    assert data["event"]["id"] == "test123"
    assert data["parsed"] is not None
    assert data["parsed"]["confidence"] == "high"
    assert data["parsed"]["person"] == "jonnie"
    assert "message" in data
    assert "Added:" in data["message"]

    # Verify calendar was called with parsed data
    mock_calendar.assert_called_once()
    call_kwargs = mock_calendar.call_args
    assert call_kwargs.kwargs["person"] == "jonnie" or call_kwargs.args[0] is not None


@pytest.mark.asyncio
async def test_add_with_source(client, mock_calendar):
    resp = await client.post("/add", json={"text": "dentist friday 2pm", "source": "ha_companion"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"


@pytest.mark.asyncio
async def test_add_default_source(client, mock_calendar):
    resp = await client.post("/add", json={"text": "meeting tomorrow 9am"})
    data = resp.json()
    assert data["status"] == "created"


# --- Low confidence / unparseable ---

@pytest.mark.asyncio
async def test_add_vague_input(client, mock_calendar):
    resp = await client.post("/add", json={"text": "groceries"})
    assert resp.status_code == 200
    data = resp.json()
    # Could be low or high - just validate schema
    assert data["status"] in ("created", "needs_confirmation")
    assert "message" in data


@pytest.mark.asyncio
async def test_add_gibberish(client, mock_calendar):
    resp = await client.post("/add", json={"text": "xkcd zzzq blargh"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("unparseable", "needs_confirmation", "created")
    assert "message" in data


# --- Response schema structure ---

@pytest.mark.asyncio
async def test_response_schema_fields(client, mock_calendar):
    resp = await client.post("/add", json={"text": "jimi haircut saturday 11am"})
    assert resp.status_code == 200
    data = resp.json()

    # All AddResponse fields present
    assert "status" in data
    assert "event" in data
    assert "parsed" in data
    assert "message" in data

    if data["status"] == "created":
        # Parsed fields
        p = data["parsed"]
        assert "title" in p
        assert "date" in p
        assert "start_time" in p
        assert "duration_minutes" in p
        assert "person" in p
        assert "confidence" in p

        # Event fields (from mock)
        e = data["event"]
        assert "id" in e
        assert "link" in e
        assert "start" in e
        assert "end" in e


# --- Parse quality checks (these hit real Gemini) ---

@pytest.mark.asyncio
async def test_parse_relative_date(client, mock_calendar):
    resp = await client.post("/add", json={"text": "dentist tomorrow 2pm"})
    data = resp.json()
    if data["status"] == "created":
        assert data["parsed"]["start_time"] == "14:00"


@pytest.mark.asyncio
async def test_parse_casual_time(client, mock_calendar):
    resp = await client.post("/add", json={"text": "dinner saturday 6"})
    data = resp.json()
    if data["status"] == "created":
        assert data["parsed"]["start_time"] == "18:00"


@pytest.mark.asyncio
async def test_parse_person_extraction(client, mock_calendar):
    resp = await client.post("/add", json={"text": "jonnie soccer friday 3pm"})
    data = resp.json()
    if data["parsed"]:
        assert data["parsed"]["person"] == "jonnie"


@pytest.mark.asyncio
async def test_parse_no_person(client, mock_calendar):
    resp = await client.post("/add", json={"text": "team meeting monday 9am"})
    data = resp.json()
    if data["parsed"]:
        assert data["parsed"]["person"] is None
