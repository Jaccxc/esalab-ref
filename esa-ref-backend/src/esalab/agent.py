"""Thin client for an `opencode serve` instance: a fresh session per ask() so generations never share context."""
from __future__ import annotations

import os
from pathlib import Path

import httpx

RULES = (Path(__file__).resolve().parents[2] / "rules" / "esalab-ieee-rules.md").read_text(encoding="utf-8")

FORMAT_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "description": "journal | conference | book | chapter | thesis | web | arxiv | other"},
        "reference": {"type": "string", "description": "the full entry without the [n] label, italics as *...*"},
        "issues": {"type": "array", "items": {"type": "string"}, "description": "missing/uncertain data the user must check"},
        "confidence": {"type": "number"},
    },
    "required": ["type", "reference", "issues", "confidence"],
}
CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "problems": {"type": "array", "items": {"type": "string"}},
        "reference": {"type": "string", "description": "corrected entry (same as input when ok)"},
    },
    "required": ["ok", "problems", "reference"],
}
SPLIT_SCHEMA = {
    "type": "object",
    "properties": {"entries": {"type": "array", "items": {"type": "string"}}},
    "required": ["entries"],
}
PARSE_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}, "first_author": {"type": "string"}, "year": {"type": "string"}},
    "required": ["title"],
}

SYSTEM = (
    "You are the reference formatter of the ESA Lab (NTPU). Follow the style rules below exactly; "
    "they override your general knowledge of IEEE style. Metadata marked match=exact comes from "
    "Crossref/OpenAlex and is trustworthy; metadata marked fuzzy or none may be a different work, so "
    "prefer the original entry's data and say so in issues. Never invent authors, pages, volumes or dates. "
    "You may use webfetch to look up a journal's ISO4/IEEE abbreviation if unsure. "
    "Write every item of issues and problems in Traditional Chinese (Taiwan usage); the reference itself stays in its original language.\n\n" + RULES
)


class Agent:
    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base = (base_url or os.environ.get("OPENCODE_URL", "http://127.0.0.1:4096")).rstrip("/")
        provider, _, model_id = (model or os.environ.get("OPENCODE_MODEL", "opencode/glm-5.3-flash-free")).partition("/")
        self.model = {"providerID": provider, "modelID": model_id}
        auth = os.environ.get("OPENCODE_SERVER_PASSWORD")
        self.http = httpx.Client(base_url=self.base, timeout=600, auth=("opencode", auth) if auth else None)
        self.session_id: str | None = None

    def healthy(self) -> bool:
        try:
            return self.http.get("/global/health").json().get("healthy", False)
        except Exception:
            return False

    def open_session(self, title: str) -> str:
        self.session_id = self.http.post("/session", json={"title": title}).json()["id"]
        return self.session_id

    def ask(self, prompt: str, schema: dict, title: str = "esalab") -> dict:
        sid = self.open_session(title)
        r = self.http.post(
            f"/session/{sid}/message",
            json={"agent": "refs", "model": self.model, "system": SYSTEM,
                  "format": {"type": "json_schema", "schema": schema},
                  "parts": [{"type": "text", "text": prompt}]},
        )
        r.raise_for_status()
        info = r.json()["info"]
        out = info.get("structured")
        if not out:
            raise RuntimeError(f"no structured output (finish={info.get('finish')}, error={info.get('error')})")
        return out
