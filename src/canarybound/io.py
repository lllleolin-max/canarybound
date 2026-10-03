"""Bounded, strict JSON loading and aggregate-only output."""
from __future__ import annotations
import json
from pathlib import Path
from decimal import Decimal
from .core import CanaryBoundError, MAX_EVENTS

MAX_MANIFEST_BYTES = 64 * 1024
MAX_LOG_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 4096


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise CanaryBoundError("duplicate JSON object field")
        result[key] = value
    return result


def _int(text):
    if len(text) > 128:
        raise CanaryBoundError("JSON integer resource limit")
    return int(text)


def loads(text):
    try:
        return json.loads(text, parse_int=_int, parse_float=Decimal,
                          object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(CanaryBoundError("nonfinite JSON")))
    except (ValueError, RecursionError, OverflowError) as exc:
        if isinstance(exc, CanaryBoundError):
            raise
        raise CanaryBoundError("malformed or excessive JSON") from exc


def read_manifest(path):
    with Path(path).open("rb") as file:
        content = file.read(MAX_MANIFEST_BYTES + 1)
    if len(content) > MAX_MANIFEST_BYTES:
        raise CanaryBoundError("manifest byte resource limit")
    try:
        return loads(content.decode("utf-8"))
    except UnicodeError as exc:
        raise CanaryBoundError("manifest must be UTF-8") from exc


def read_events(path):
    total = 0
    with Path(path).open("rb") as file:
        for index in range(MAX_EVENTS + 1):
            line = file.readline(MAX_LINE_BYTES + 1)
            if not line:
                return
            total += len(line)
            if index >= MAX_EVENTS or len(line) > MAX_LINE_BYTES or total > MAX_LOG_BYTES:
                raise CanaryBoundError("event log resource limit")
            try:
                yield loads(line.decode("utf-8"))
            except UnicodeError as exc:
                raise CanaryBoundError("event log must be UTF-8") from exc


def protect_output(output, inputs):
    target = Path(output).resolve()
    for source in inputs:
        origin = Path(source).resolve()
        if target == origin or (target.exists() and origin.exists() and target.samefile(origin)):
            raise CanaryBoundError("output aliases an input file")
    return target
