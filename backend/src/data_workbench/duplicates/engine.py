from __future__ import annotations

import hashlib
from itertools import combinations

import duckdb
from rapidfuzz import fuzz, utils

from data_workbench.domain.duplicates import (
    DuplicateCandidate,
    DuplicateConfig,
    DuplicateGroup,
)
from data_workbench.engine.sql import quote_identifier, quote_literal
from data_workbench.ingest.base import SYSTEM_COLUMNS, TableHandle

MAX_BLOCK_ROWS = 50
MAX_FETCH_ROWS = 10_000
BLOCK_SEPARATOR = "\x1f"


class InvalidDuplicateConfig(ValueError):
    """Raised when a duplicate search configuration is unusable."""


def _column_names(connection: duckdb.DuckDBPyConnection, sql: str) -> list[str]:
    described = connection.sql(f"DESCRIBE SELECT * FROM ({sql})").fetchall()
    return [str(row[0]) for row in described]


def _visible(connection: duckdb.DuckDBPyConnection, scan_sql: str) -> str:
    hidden = [
        name
        for name in _column_names(connection, scan_sql)
        if name in SYSTEM_COLUMNS
    ]
    if not hidden:
        return scan_sql
    excluded = ", ".join(quote_identifier(name) for name in hidden)
    return f"SELECT * EXCLUDE ({excluded}) FROM ({scan_sql})"


def _similarity(left: str | None, right: str | None) -> float:
    if left is None and right is None:
        return 1.0
    if left is None or right is None:
        return 0.0
    return (
        fuzz.token_sort_ratio(left, right, processor=utils.default_process) / 100.0
    )


def _group_id(row_ids: list[str]) -> str:
    material = "|".join(sorted(row_ids, key=int))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


class DuplicateEngine:
    def __init__(
        self,
        max_block_rows: int = MAX_BLOCK_ROWS,
        max_fetch_rows: int = MAX_FETCH_ROWS,
    ) -> None:
        self.max_block_rows = max_block_rows
        self.max_fetch_rows = max_fetch_rows

    def _validate_columns(
        self,
        connection: duckdb.DuckDBPyConnection,
        base: str,
        required: list[str],
    ) -> None:
        known = set(_column_names(connection, base))
        missing = [name for name in required if name not in known]
        if missing:
            raise InvalidDuplicateConfig(
                f"unknown columns: {', '.join(sorted(missing))}"
            )

    def find_fuzzy(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        config: DuplicateConfig,
        max_candidates: int,
    ) -> list[DuplicateGroup]:
        if not config.blocking_columns or not config.comparison_weights:
            raise InvalidDuplicateConfig(
                "blocking and comparison columns are required"
            )
        base = _visible(connection, handle.scan_sql)
        fields = sorted(config.comparison_weights)
        self._validate_columns(
            connection, base, [*config.blocking_columns, *fields]
        )
        block_expr = f" || {quote_literal(BLOCK_SEPARATOR)} || ".join(
            f"coalesce(lower(trim(CAST({quote_identifier(name)} AS VARCHAR))), '')"
            for name in config.blocking_columns
        )
        selected = ", ".join(
            f"CAST({quote_identifier(name)} AS VARCHAR)" for name in fields
        )
        rows = connection.sql(
            f"WITH keyed AS ("
            f"SELECT row_number() OVER () AS rid, {block_expr} AS blk,"
            f" {selected} FROM ({base}))"
            f" SELECT * FROM keyed WHERE blk IN ("
            f"SELECT blk FROM keyed GROUP BY blk"
            f" HAVING count(*) BETWEEN 2 AND {self.max_block_rows})"
            f" ORDER BY blk, rid LIMIT {self.max_fetch_rows}"
        ).fetchall()
        blocks: dict[str, list[tuple[str, dict[str, str | None]]]] = {}
        for row in rows:
            rid, block = str(row[0]), str(row[1])
            values = dict(zip(fields, row[2:]))
            blocks.setdefault(block, []).append((rid, values))
        total_weight = sum(config.comparison_weights.values())
        if total_weight <= 0:
            raise InvalidDuplicateConfig("comparison weights must be positive")
        accepted: list[DuplicateCandidate] = []
        candidate_count = 0
        for block in sorted(blocks):
            for (left_id, left), (right_id, right) in combinations(
                blocks[block], 2
            ):
                if candidate_count >= max_candidates:
                    break
                candidate_count += 1
                evidence = {
                    field: _similarity(left.get(field), right.get(field))
                    for field in fields
                }
                confidence = (
                    sum(
                        config.comparison_weights[field] * evidence[field]
                        for field in fields
                    )
                    / total_weight
                )
                if confidence >= config.threshold:
                    accepted.append(
                        DuplicateCandidate(
                            left_row_id=left_id,
                            right_row_id=right_id,
                            confidence=confidence,
                            evidence=evidence,
                        )
                    )
        row_values = {
            rid: values for members in blocks.values() for rid, values in members
        }
        return self._group(accepted, row_values, fields)

    def _group(
        self,
        candidates: list[DuplicateCandidate],
        row_values: dict[str, dict[str, str | None]],
        fields: list[str],
    ) -> list[DuplicateGroup]:
        parent: dict[str, str] = {}

        def find(row_id: str) -> str:
            parent.setdefault(row_id, row_id)
            while parent[row_id] != row_id:
                parent[row_id] = parent[parent[row_id]]
                row_id = parent[row_id]
            return row_id

        for candidate in candidates:
            parent[find(candidate.left_row_id)] = find(candidate.right_row_id)
        members: dict[str, list[DuplicateCandidate]] = {}
        for candidate in sorted(
            candidates,
            key=lambda item: (int(item.left_row_id), int(item.right_row_id)),
        ):
            members.setdefault(find(candidate.left_row_id), []).append(candidate)
        groups: list[DuplicateGroup] = []
        for group_candidates in members.values():
            row_ids = sorted(
                {
                    row_id
                    for candidate in group_candidates
                    for row_id in (candidate.left_row_id, candidate.right_row_id)
                },
                key=int,
            )
            evidence = {
                field: max(
                    candidate.evidence.get(field, 0.0)
                    for candidate in group_candidates
                )
                for field in fields
            }
            display_values = [
                " | ".join(
                    "" if row_values[row_id].get(field) is None
                    else str(row_values[row_id][field])
                    for field in fields
                )
                for row_id in row_ids
            ]
            groups.append(
                DuplicateGroup(
                    id=_group_id(row_ids),
                    row_ids=row_ids,
                    candidates=group_candidates,
                    display_values=display_values,
                    confidence=max(
                        candidate.confidence for candidate in group_candidates
                    ),
                    evidence=evidence,
                    decision=None,
                )
            )
        return sorted(groups, key=lambda group: int(group.row_ids[0]))

    def find_exact(
        self,
        connection: duckdb.DuckDBPyConnection,
        handle: TableHandle,
        columns: list[str],
        max_groups: int = 100,
    ) -> list[DuplicateGroup]:
        if not columns:
            raise InvalidDuplicateConfig("exact matching requires columns")
        base = _visible(connection, handle.scan_sql)
        self._validate_columns(connection, base, columns)
        quoted = ", ".join(quote_identifier(name) for name in columns)
        rows = connection.sql(
            f"WITH keyed AS ("
            f"SELECT row_number() OVER () AS rid, * FROM ({base}))"
            f" SELECT list(rid ORDER BY rid), {quoted} FROM keyed"
            f" GROUP BY {quoted} HAVING count(*) > 1"
            f" ORDER BY min(rid) LIMIT {max_groups}"
        ).fetchall()
        groups: list[DuplicateGroup] = []
        for row in rows:
            row_ids = [str(rid) for rid in row[0]]
            display = " | ".join(
                "" if value is None else str(value) for value in row[1:]
            )
            first = row_ids[0]
            candidates = [
                DuplicateCandidate(
                    left_row_id=first,
                    right_row_id=other,
                    confidence=1.0,
                    evidence={name: 1.0 for name in columns},
                )
                for other in row_ids[1:]
            ]
            groups.append(
                DuplicateGroup(
                    id=_group_id(row_ids),
                    row_ids=row_ids,
                    candidates=candidates,
                    display_values=[display for _ in row_ids],
                    confidence=1.0,
                    evidence={name: 1.0 for name in columns},
                    decision=None,
                )
            )
        return groups
