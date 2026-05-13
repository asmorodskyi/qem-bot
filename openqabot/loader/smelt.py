# Copyright SUSE LLC
# SPDX-License-Identifier: MIT
"""SMELT loader."""

from __future__ import annotations

import json
from concurrent import futures
from logging import getLogger
from pathlib import Path
from typing import Any, cast

from jsonschema import ValidationError, validate

from openqabot import config
from openqabot.utils import retry10 as retried_requests
from openqabot.utils import walk

log = getLogger("bot.loader.smelt")


class _SmeltQueries:
    """Lazy loader for SMELT GraphQL queries and JSON schemas from disk."""

    def __init__(self) -> None:
        self._active_fst: str | None = None
        self._active_next: str | None = None
        self._incident: str | None = None
        self._active_inc_schema: dict[str, Any] | None = None
        self._incident_schema: dict[str, Any] | None = None
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        qdir = config.settings.smelt_queries_dir
        self._active_fst = self._read_text(qdir / "active_first.graphql")
        self._active_next = self._read_text(qdir / "active_next.graphql")
        self._incident = self._read_text(qdir / "incident.graphql")
        self._active_inc_schema = self._read_json(qdir / "active_incidents_schema.json")
        self._incident_schema = self._read_json(qdir / "incident_schema.json")
        self._loaded = True

    @staticmethod
    def _read_text(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError, OSError):
            log.warning("Failed to load SMELT query file: %s", path)
            return None

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            with path.open(encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, PermissionError, OSError):
            log.warning("Failed to load SMELT schema file: %s", path)
            return None
        except json.JSONDecodeError:
            log.warning("Failed to parse SMELT schema file: %s", path)
            return None

    def _reset(self) -> None:
        self._loaded = False
        self._active_fst = None
        self._active_next = None
        self._incident = None
        self._active_inc_schema = None
        self._incident_schema = None

    @property
    def ACTIVE_FST(self) -> str | None:
        self._load()
        return self._active_fst

    @property
    def ACTIVE_NEXT(self) -> str | None:
        self._load()
        return self._active_next

    @property
    def INCIDENT(self) -> str | None:
        self._load()
        return self._incident

    @property
    def ACTIVE_INC_SCHEMA(self) -> dict[str, Any] | None:
        self._load()
        return self._active_inc_schema

    @property
    def INCIDENT_SCHEMA(self) -> dict[str, Any] | None:
        self._load()
        return self._incident_schema


_queries = _SmeltQueries()


def __getattr__(name: str) -> Any:
    _QUERY_ATTRS = {"ACTIVE_FST", "ACTIVE_NEXT", "INCIDENT", "ACTIVE_INC_SCHEMA", "INCIDENT_SCHEMA"}
    if name in _QUERY_ATTRS:
        return getattr(_queries, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def get_json(query: str, host: str | None = None) -> dict[str, Any]:
    """Fetch JSON data from SMELT using a GraphQL query."""
    host = host or config.settings.smelt_graphql
    return retried_requests.get(host, params={"query": query}, verify=not config.settings.insecure).json()


def get_active_submission_ids() -> set[int]:
    """Get active incidents from SMELT GraphQL API."""
    if _queries.ACTIVE_FST is None or _queries.ACTIVE_NEXT is None or _queries.ACTIVE_INC_SCHEMA is None:
        log.error("SMELT query files not loaded, cannot fetch active incidents")
        return set()

    active: set[int] = set()

    has_next = True
    cursor = None

    while has_next:
        query = _queries.ACTIVE_NEXT % {"cursor": cursor} if cursor else _queries.ACTIVE_FST
        ndata = get_json(query)
        try:
            validate(instance=ndata, schema=_queries.ACTIVE_INC_SCHEMA)
        except ValidationError:
            log.exception("SMELT API error: Invalid data structure received for active incidents")
            return set()
        incidents = ndata["data"]["incidents"]
        active.update(x["node"]["incidentId"] for x in incidents["edges"])
        has_next = incidents["pageInfo"]["hasNextPage"]
        if has_next:
            cursor = incidents["pageInfo"]["endCursor"]

    log.info("Loaded %s active incidents from SMELT", len(active))

    return active


def get_submission_from_smelt(incident: int) -> dict[str, Any] | None:
    """Fetch detailed information for a single submission from SMELT."""
    if _queries.INCIDENT is None or _queries.INCIDENT_SCHEMA is None:
        log.error("SMELT query files not loaded, cannot fetch incident details")
        return None

    query = _queries.INCIDENT % {"incident": incident}

    log.info("Fetching details for SMELT incident smelt:%s", incident)
    inc_result = get_json(query)
    try:
        validate(instance=inc_result, schema=_queries.INCIDENT_SCHEMA)
        inc_result = cast("dict[str, Any]", walk(inc_result["data"]["incidents"]["edges"][0]["node"]))
    except ValidationError:
        log.exception("SMELT API error: Invalid data for SMELT incident smelt:%s", incident)
        return None
    except Exception:
        log.exception("SMELT API error: Unexpected error for SMELT incident smelt:%s", incident)
        return None

    return inc_result


def get_submissions(active: set[int]) -> list[dict[str, Any]]:
    """Fetch detailed information for a set of submissions from SMELT in parallel."""
    with futures.ThreadPoolExecutor() as executor:
        future_sub = [executor.submit(get_submission_from_smelt, inc) for inc in active]
        submissions = (future.result() for future in futures.as_completed(future_sub))
        return [sub for sub in submissions if sub]
