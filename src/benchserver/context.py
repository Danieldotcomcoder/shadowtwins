"""Shared application context: settings, provider adapters and benchmark lookups."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from benchcore import registry
from benchcore.interface import BenchmarkModule

from . import db
from .config import Settings
from .providers.base import Provider
from .providers.groq import PREFIX as GROQ_PREFIX
from .providers.groq import GroqProvider
from .providers.mock import MockProvider
from .providers.openrouter import OpenRouterProvider


class AppContext:
    def __init__(self, settings: Settings, providers: dict[str, Provider] | None = None) -> None:
        self.settings = settings
        self._prompt_index: dict[str, str] | None = None
        if providers is None:
            providers = {"openrouter": OpenRouterProvider(
                settings.openrouter_api_key, settings.openrouter_base_url,
                timeout_s=settings.http_timeout_s, connect_timeout_s=settings.connect_timeout_s,
                app_title=settings.app_title)}
            if settings.groq_configured:  # Groq's catalog needs the key, so no key means no Groq models
                providers["groq"] = GroqProvider(
                    settings.groq_api_key, settings.groq_base_url, plan=settings.groq_plan,
                    timeout_s=settings.http_timeout_s, connect_timeout_s=settings.connect_timeout_s)
            if settings.enable_mock_provider:
                providers["mock"] = MockProvider(self.answer_book)
        self.providers = providers

    # --- database ------------------------------------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        return db.connect(self.settings.db_path)

    # --- providers -----------------------------------------------------------------------------
    @staticmethod
    def provider_name_for(model_id: str) -> str:
        if model_id.startswith("mock/"):
            return "mock"
        if model_id.startswith(GROQ_PREFIX):
            return "groq"
        return "openrouter"

    def provider_for(self, model_id: str) -> Provider:
        name = self.provider_name_for(model_id)
        if name not in self.providers:
            raise LookupError(f"provider '{name}' is not enabled on this server")
        return self.providers[name]

    # --- benchmark objects -------------------------------------------------------------------
    @staticmethod
    def module(benchmark_id: str) -> BenchmarkModule:
        return registry.get(benchmark_id)

    def load_item(self, conn: sqlite3.Connection, instance_id: str) -> tuple[BenchmarkModule, BaseModel, BaseModel, dict[str, Any]]:
        row = conn.execute(
            "SELECT i.*, c.core_hash, c.max_objective, c.certificate_json, c.verified FROM instances i "
            "JOIN certificates c USING(instance_id) WHERE instance_id=?", (instance_id,)).fetchone()
        if row is None:
            raise KeyError(instance_id)
        module = self.module(row["benchmark_id"])
        inst = module.load_instance(db.jload(row["instance_json"]))
        cert = module.load_certificate(db.jload(row["certificate_json"]))
        return module, inst, cert, dict(row)

    # --- mock answer book (test double support only) ----------------------------------------
    def answer_book(self, prompt_text: str) -> tuple[str | None, Callable[[int], str | None]] | None:
        key = hashlib.sha256(prompt_text.encode()).hexdigest()
        conn = self.connect()
        try:
            if self._prompt_index is None or key not in self._prompt_index:
                self._prompt_index = {}
                for row in conn.execute("SELECT instance_id, benchmark_id, instance_json FROM instances"):
                    module = self.module(row["benchmark_id"])
                    inst = module.load_instance(db.jload(row["instance_json"]))
                    text = module.render_prompt(inst).messages[-1].content
                    self._prompt_index[hashlib.sha256(text.encode()).hexdigest()] = row["instance_id"]
            iid = self._prompt_index.get(key)
            if iid is None:
                return None
            module, inst, cert, _ = self.load_item(conn, iid)
        finally:
            conn.close()
        return module.reference_answer(inst, cert), lambda seed: module.sample_answer(inst, seed)

    async def aclose(self) -> None:
        for p in self.providers.values():
            await p.aclose()
