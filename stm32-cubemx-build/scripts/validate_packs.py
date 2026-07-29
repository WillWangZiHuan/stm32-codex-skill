#!/usr/bin/env python3
"""Validate independently contributed STM32 capability packs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PACK_ID = re.compile(r"^[a-z][a-z0-9_]*$")
TEMPLATE_TOKEN = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
OPERATION_INSTANCE_PREFIX = re.compile(r"^[A-Z][A-Z0-9]*$")
DIRECT_PIN_SIGNAL = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
OPERATION_SIGNAL_SUFFIX = re.compile(r"^[A-Z][A-Z0-9]*$")
PACKS_ROOT = Path(__file__).resolve().parents[1] / "packs"
SUPPORTED_IOC_OVERRIDE_KINDS = frozenset({"gpio-initial-state", "gpio-input-pull", "timer-nvic-enable"})
SUPPORTED_BINDING_TYPES = frozenset({"identifier", "gpio-level", "uint"})
PACK_MANIFEST_SCHEMA_VERSION = 5
PLAN_RESOURCE_FIELDS = frozenset(
    {
        "operation_instance_prefixes",
        "direct_pin_signals",
        "required_operation_signal_suffixes",
        "minimum_operation_pins",
    }
)


class PackValidationError(ValueError):
    """Raised when one pack breaks the stable pack contract."""


def nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise PackValidationError(f"{label} must be a non-empty string.")
    return value


def nonempty_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise PackValidationError(f"{label} must be a non-empty list.")
    return [nonempty_string(item, f"{label}[{index}]") for index, item in enumerate(value, start=1)]


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise PackValidationError(f"{label} must be a list.")
    return [nonempty_string(item, f"{label}[{index}]") for index, item in enumerate(value, start=1)]


def unique_contract_tokens(value: Any, label: str, pattern: re.Pattern[str]) -> list[str]:
    tokens = string_list(value, label)
    seen: set[str] = set()
    for token in tokens:
        if not pattern.fullmatch(token):
            raise PackValidationError(f"{label} contains an unsupported resource token: {token}")
        if token in seen:
            raise PackValidationError(f"{label} repeats resource token: {token}")
        seen.add(token)
    return tokens


def nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PackValidationError(f"{label} must be a non-negative integer.")
    return value


def validate_plan_resources(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PackValidationError(f"{label} must be an object.")
    keys = set(value)
    if keys != PLAN_RESOURCE_FIELDS:
        missing = sorted(PLAN_RESOURCE_FIELDS - keys)
        unexpected = sorted(keys - PLAN_RESOURCE_FIELDS)
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected {', '.join(unexpected)}")
        raise PackValidationError(f"{label} must declare exactly the stable resource fields ({'; '.join(details)}).")
    required_suffixes = unique_contract_tokens(
        value["required_operation_signal_suffixes"],
        f"{label}.required_operation_signal_suffixes",
        OPERATION_SIGNAL_SUFFIX,
    )
    minimum_operation_pins = nonnegative_integer(
        value["minimum_operation_pins"],
        f"{label}.minimum_operation_pins",
    )
    if minimum_operation_pins < len(required_suffixes):
        raise PackValidationError(
            f"{label}.minimum_operation_pins must be at least the number of "
            "required_operation_signal_suffixes."
        )
    return {
        "operation_instance_prefixes": unique_contract_tokens(
            value["operation_instance_prefixes"],
            f"{label}.operation_instance_prefixes",
            OPERATION_INSTANCE_PREFIX,
        ),
        "direct_pin_signals": unique_contract_tokens(
            value["direct_pin_signals"],
            f"{label}.direct_pin_signals",
            DIRECT_PIN_SIGNAL,
        ),
        "required_operation_signal_suffixes": required_suffixes,
        "minimum_operation_pins": minimum_operation_pins,
    }


def safe_pack_relative_path(value: str, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise PackValidationError(f"{label} must be a path inside its pack.")
    return path


def validate_pack(pack_dir: Path) -> dict[str, Any]:
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.is_file():
        raise PackValidationError(f"{pack_dir.name}: manifest.json is missing.")
    if not (pack_dir / "PACK.md").is_file():
        raise PackValidationError(f"{pack_dir.name}: PACK.md is missing.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PackValidationError(f"{pack_dir.name}: manifest.json is invalid JSON: {error.msg}") from error
    if not isinstance(manifest, dict):
        raise PackValidationError(f"{pack_dir.name}: manifest.json must contain an object.")
    if manifest.get("schema_version") != PACK_MANIFEST_SCHEMA_VERSION:
        raise PackValidationError(
            f"{pack_dir.name}: schema_version must be {PACK_MANIFEST_SCHEMA_VERSION}."
        )
    pack_id = nonempty_string(manifest.get("id"), f"{pack_dir.name}.id")
    if not PACK_ID.fullmatch(pack_id):
        raise PackValidationError(f"{pack_dir.name}: id must use lowercase letters, numbers, or underscores.")
    if pack_id != pack_dir.name:
        raise PackValidationError(f"{pack_dir.name}: id must match its directory name ({pack_dir.name}).")
    nonempty_string(manifest.get("summary"), f"{pack_id}.summary")
    nonempty_string_list(manifest.get("requires"), f"{pack_id}.requires")
    templates = nonempty_string_list(manifest.get("templates"), f"{pack_id}.templates")
    binding_types = manifest.get("binding_types")
    if not isinstance(binding_types, dict):
        raise PackValidationError(f"{pack_id}.binding_types must be an object.")
    for binding_name, binding_type in binding_types.items():
        if not isinstance(binding_name, str) or not TEMPLATE_TOKEN.fullmatch("{{" + binding_name + "}}"):
            raise PackValidationError(f"{pack_id}.binding_types contains an invalid template token name.")
        if binding_type not in SUPPORTED_BINDING_TYPES:
            raise PackValidationError(f"{pack_id}.binding_types.{binding_name} has unsupported type {binding_type!r}.")
    nonempty_string_list(manifest.get("verifications"), f"{pack_id}.verifications")
    manifest["plan_resources"] = validate_plan_resources(manifest.get("plan_resources"), f"{pack_id}.plan_resources")
    override_kinds = string_list(manifest.get("ioc_override_kinds"), f"{pack_id}.ioc_override_kinds")
    seen_override_kinds: set[str] = set()
    for override_kind in override_kinds:
        if override_kind not in SUPPORTED_IOC_OVERRIDE_KINDS:
            raise PackValidationError(f"{pack_id}: unsupported ioc_override_kinds value: {override_kind}")
        if override_kind in seen_override_kinds:
            raise PackValidationError(f"{pack_id}: ioc_override_kinds repeats {override_kind}")
        seen_override_kinds.add(override_kind)
    template_paths: list[Path] = []
    for template in templates:
        path = safe_pack_relative_path(template, f"{pack_id}.templates")
        if not (pack_dir / path).is_file():
            raise PackValidationError(f"{pack_id}: declared template is missing: {template}")
        template_paths.append(path)
    headers = [path for path in template_paths if path.name.endswith(".h.tmpl")]
    sources = [path for path in template_paths if path.name.endswith(".c.tmpl")]
    if len(headers) != 1 or len(sources) != 1:
        raise PackValidationError(f"{pack_id}: templates must declare exactly one .h.tmpl and one .c.tmpl.")
    for path in template_paths:
        try:
            template_text = (pack_dir / path).read_text(encoding="utf-8")
        except OSError as error:
            raise PackValidationError(f"{pack_id}: could not read declared template {path}: {error}") from error
        remainder = TEMPLATE_TOKEN.sub("", template_text)
        if "{{" in remainder or "}}" in remainder:
            raise PackValidationError(f"{pack_id}: template has a malformed placeholder: {path}")
    external_tokens: set[str] = set()
    for path in template_paths:
        external_tokens.update(TEMPLATE_TOKEN.findall((pack_dir / path).read_text(encoding="utf-8")))
    external_tokens -= {"MODULE_NAME", "MODULE_GUARD"}
    if set(binding_types) != external_tokens:
        missing = sorted(external_tokens - set(binding_types))
        unexpected = sorted(set(binding_types) - external_tokens)
        details: list[str] = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected {', '.join(unexpected)}")
        raise PackValidationError(f"{pack_id}.binding_types must match template bindings ({'; '.join(details)}).")
    return manifest


def validate_packs(packs_root: Path = PACKS_ROOT) -> list[str]:
    if not packs_root.is_dir():
        raise PackValidationError(f"Packs directory is missing: {packs_root}")
    pack_dirs = sorted(path for path in packs_root.iterdir() if path.is_dir())
    if not pack_dirs:
        raise PackValidationError("No capability packs were found.")
    seen_ids: set[str] = set()
    validated: list[str] = []
    for pack_dir in pack_dirs:
        manifest = validate_pack(pack_dir)
        pack_id = manifest["id"]
        if pack_id in seen_ids:
            raise PackValidationError(f"Duplicate pack id: {pack_id}")
        seen_ids.add(pack_id)
        validated.append(pack_id)
    return validated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packs-root", help="Override the packs directory for validation.")
    args = parser.parse_args()
    try:
        root = Path(args.packs_root).expanduser().resolve() if args.packs_root else PACKS_ROOT
        identifiers = validate_packs(root)
    except PackValidationError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    print(f"Validated {len(identifiers)} pack(s): {', '.join(identifiers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
