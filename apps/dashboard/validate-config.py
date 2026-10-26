#!/usr/bin/env python3
"""Validate the dashboard runtime configuration without echoing values."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

_MISSING = object()


class ConfigError(ValueError):
    """Raised when the dashboard configuration does not match the contract."""


def _fail(path: str, message: str) -> None:
    raise ConfigError(f"{path}: {message}")


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    return value


def _get(mapping: dict[str, Any], key: str, path: str, required: bool = False) -> Any:
    if key not in mapping:
        if required:
            _fail(f"{path}.{key}", "is required")
        return _MISSING
    return mapping[key]


def _check_number(
    value: Any,
    path: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "must be a finite number")
    if not math.isfinite(value):
        _fail(path, "must be a finite number")
    if minimum is not None and value < minimum:
        _fail(path, f"must be >= {minimum}")
    if maximum is not None and value > maximum:
        _fail(path, f"must be <= {maximum}")


def _check_int(
    value: Any,
    path: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "must be an integer")
    if minimum is not None and value < minimum:
        _fail(path, f"must be >= {minimum}")
    if maximum is not None and value > maximum:
        _fail(path, f"must be <= {maximum}")


def _check_string(value: Any, path: str, non_empty: bool = True) -> None:
    if not isinstance(value, str):
        _fail(path, "must be a string")
    if non_empty and not value.strip():
        _fail(path, "must not be empty")


def _check_boolean(value: Any, path: str) -> None:
    if not isinstance(value, bool):
        _fail(path, "must be a boolean")


def _check_enum(value: Any, path: str, allowed: tuple[Any, ...]) -> None:
    if value not in allowed:
        rendered = ", ".join(repr(item) for item in allowed)
        _fail(path, f"must be one of: {rendered}")


def _check_location(location: Any, path: str, latitude_key: str, longitude_key: str) -> None:
    location = _require_mapping(location, path)
    _check_number(_get(location, latitude_key, path, required=True), f"{path}.{latitude_key}", -90, 90)
    _check_number(
        _get(location, longitude_key, path, required=True), f"{path}.{longitude_key}", -180, 180
    )


def validate_config(data: Any) -> None:
    """Validate the JSON-compatible dashboard configuration in place."""
    root = _require_mapping(data, "$")

    bus = _require_mapping(_get(root, "bus", "$", required=True), "bus")
    stops = _get(bus, "stops", "bus", required=True)
    if not isinstance(stops, list):
        _fail("bus.stops", "must be an array")
    for index, stop in enumerate(stops):
        stop_path = f"bus.stops[{index}]"
        stop = _require_mapping(stop, stop_path)
        _check_string(_get(stop, "id", stop_path, required=True), f"{stop_path}.id")
        _check_string(_get(stop, "name", stop_path, required=True), f"{stop_path}.name")
        lines = _get(stop, "lines", stop_path)
        if lines is not _MISSING:
            if not isinstance(lines, list):
                _fail(f"{stop_path}.lines", "must be an array")
            for line_index, line in enumerate(lines):
                _check_string(line, f"{stop_path}.lines[{line_index}]")
        limit = _get(stop, "limit", stop_path)
        if limit is not _MISSING:
            _check_int(limit, f"{stop_path}.limit", 1, 20)
        refetch = _get(stop, "refetchIntervalMs", stop_path)
        if refetch is not _MISSING:
            _check_int(refetch, f"{stop_path}.refetchIntervalMs", 0)

    flights = _require_mapping(_get(root, "flights", "$", required=True), "flights")
    _check_location(
        _get(flights, "location", "flights", required=True),
        "flights.location",
        "lat",
        "lng",
    )
    location = flights["location"]
    _check_number(
        _get(location, "radiusKm", "flights.location", required=True),
        "flights.location.radiusKm",
        1e-9,
    )
    auto_refresh = _get(flights, "autoRefresh", "flights")
    if auto_refresh is not _MISSING:
        _check_enum(auto_refresh, "flights.autoRefresh", ("off", 5, 10, 30, 60))
    max_results = _get(flights, "maxResults", "flights")
    if max_results is not _MISSING:
        _check_int(max_results, "flights.maxResults", 1, 20)
    debug_map = _get(flights, "debugMap", "flights")
    if debug_map is not _MISSING:
        _check_boolean(debug_map, "flights.debugMap")

    weather = _require_mapping(_get(root, "weather", "$", required=True), "weather")
    _check_location(
        _get(weather, "location", "weather", required=True),
        "weather.location",
        "latitude",
        "longitude",
    )
    weather_location = weather["location"]
    _check_string(
        _get(weather_location, "name", "weather.location", required=True),
        "weather.location.name",
    )
    _check_string(
        _get(weather_location, "timezone", "weather.location", required=True),
        "weather.location.timezone",
    )
    country = _get(weather_location, "country", "weather.location")
    if country is not _MISSING:
        _check_string(country, "weather.location.country", non_empty=False)
    refetch = _get(weather, "refetchIntervalMs", "weather")
    if refetch is not _MISSING:
        _check_int(refetch, "weather.refetchIntervalMs", 0)

    clock = _get(root, "clock", "$")
    if clock is not _MISSING:
        clock = _require_mapping(clock, "clock")
        default_format = _get(clock, "defaultFormat", "clock")
        if default_format is not _MISSING:
            _check_enum(default_format, "clock.defaultFormat", ("12h", "24h"))
        switchable = _get(clock, "switchable", "clock")
        if switchable is not _MISSING:
            _check_boolean(switchable, "clock.switchable")
        align = _get(clock, "align", "clock")
        if align is not _MISSING:
            _check_enum(align, "clock.align", ("left", "center", "right"))

    tasks = _get(root, "tasks", "$")
    if tasks is not _MISSING:
        tasks = _require_mapping(tasks, "tasks")
        filters = _get(tasks, "filters", "tasks")
        if filters is not _MISSING:
            _require_mapping(filters, "tasks.filters")
        refresh_rate = _get(tasks, "refreshRateMs", "tasks")
        if refresh_rate is not _MISSING:
            _check_int(refresh_rate, "tasks.refreshRateMs", 0)
        auto_rotate = _get(tasks, "autoRotateMs", "tasks")
        if auto_rotate is not _MISSING:
            _check_int(auto_rotate, "tasks.autoRotateMs", 0)
        transition = _get(tasks, "transitionVariant", "tasks")
        if transition is not _MISSING:
            _check_string(transition, "tasks.transitionVariant")
        slide_duration = _get(tasks, "slideDurationMs", "tasks")
        if slide_duration is not _MISSING:
            _check_int(slide_duration, "tasks.slideDurationMs", 0)

    status = _get(root, "status", "$")
    if status is not _MISSING:
        status = _require_mapping(status, "status")
        interval = _get(status, "intervalMs", "status")
        if interval is not _MISSING:
            _check_int(interval, "status.intervalMs", 1)

    placeholders = _get(root, "placeholders", "$")
    if placeholders is not _MISSING:
        if not isinstance(placeholders, list):
            _fail("placeholders", "must be an array")
        for index, placeholder in enumerate(placeholders):
            placeholder_path = f"placeholders[{index}]"
            placeholder = _require_mapping(placeholder, placeholder_path)
            _check_string(
                _get(placeholder, "title", placeholder_path, required=True),
                f"{placeholder_path}.title",
            )
            _check_string(
                _get(placeholder, "description", placeholder_path, required=True),
                f"{placeholder_path}.description",
            )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: validate-config.py <config.json>", file=sys.stderr)
        return 2

    path = Path(args[0])
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        print(f"{path}: file not found", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"{path}: invalid JSON at line {exc.lineno} column {exc.colno}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"{path}: cannot read file: {exc.strerror}", file=sys.stderr)
        return 1

    try:
        validate_config(data)
    except ConfigError as exc:
        print(f"{path}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
