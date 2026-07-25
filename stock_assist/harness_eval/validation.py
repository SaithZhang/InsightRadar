"""Shared bounded identifier, reference, privacy, and file-read validation."""

from __future__ import annotations

from math import isfinite
from pathlib import Path
import re


MAX_IDENTIFIER_LENGTH = 64
MAX_REFERENCE_LENGTH = 128
MAX_PUBLIC_STRING_LENGTH = 256
MAX_PUBLIC_DEPTH = 5
MAX_PUBLIC_CONTAINER_ITEMS = 32
MAX_PUBLIC_CONTAINERS = 64
MAX_PUBLIC_NUMERIC_MAGNITUDE = 1_000_000

IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
REFERENCE = re.compile(r"^[A-Za-z0-9.][A-Za-z0-9._/-]{0,127}$")
TRAVERSAL = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)")
URL_VALUE = re.compile(r"(?i)(?:https?|file)://")
PATH_COMPONENT_PUNCTUATION = frozenset("._-~$")
CREDENTIAL_VALUE_PATTERNS = (
    re.compile(r"(?i)(?<![A-Za-z0-9])bearer\s+[A-Za-z0-9._-]{8,200}(?![A-Za-z0-9])"),
    re.compile(r"(?i)(?<![A-Za-z0-9])(?:sk|pk)-[A-Za-z0-9_-]{8,200}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,64}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{40,120}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])glpat-[A-Za-z0-9_-]{20,64}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])x(?:ox[baprs]|app)-[A-Za-z0-9-]{10,200}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])AIza[A-Za-z0-9_-]{35}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])npm_[A-Za-z0-9]{36}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])pypi-[A-Za-z0-9_-]{50,200}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])(?:sk|rk)_live_[A-Za-z0-9]{16,128}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])SK[0-9a-fA-F]{32}(?![A-Za-z0-9])"),
    re.compile(
        r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{10,100}\.[A-Za-z0-9_-]{10,100}\."
        r"[A-Za-z0-9_-]{10,100}(?![A-Za-z0-9_-])"
    ),
)
SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:password|pass[-_ ]?wd|pwd|token|secret|"
    r"api[-_ ]?key|access[-_ ]?key|credential(?:s)?|session(?:[-_ ]?id)?|"
    r"account(?:[-_ ]?(?:id|identifier|number))?|cookie|authorization|auth)\s*[:=]"
)
PRIVATE_VALUE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:portfolio|holdings?|positions?|shares?|"
    r"broker[-_ ]?(?:export|account)|account[-_ ]?(?:id|identifier|number)|"
    r"cost[-_ ]?basis|personal[-_ ]?risk|risk[-_ ]?(?:profile|tolerance)|"
    r"loss[-_ ]?tolerance|"
    r"raw[-_ ]?conversation|chat[-_ ]?history|reasoning|"
    r"chain[-_ ]?of[-_ ]?thought|hidden[-_ ]?reasoning|thought[-_ ]?process)"
    r"(?![A-Za-z0-9])|"
    "(?:\u6301\u4ed3|\u4ed3\u4f4d|\u6301\u80a1|\u80a1\u6570|\u80a1\u7968\u6570\u91cf|\u5238\u5546\u5bfc\u51fa|"
    "\u5238\u5546\u8d26\u6237|\u8d26\u6237\u6807\u8bc6|\u8d26\u53f7|"
    "\u6210\u672c\u4ef7|\u6210\u672c\u57fa\u7840|\u4e2a\u4eba\u98ce\u9669|"
    "\u98ce\u9669\u753b\u50cf|\u98ce\u9669\u504f\u597d|\u98ce\u9669\u627f\u53d7|"
    "\u539f\u59cb\u5bf9\u8bdd|\u804a\u5929\u8bb0\u5f55|"
    "\u63a8\u7406|\u601d\u7ef4\u94fe)"
)
ASCII_WORD = re.compile(r"[A-Za-z]+")
ENGLISH_TRADE_AUTHORITY_LEXEMES = frozenset(
    {
        "buy",
        "buys",
        "buying",
        "buyer",
        "buyers",
        "sell",
        "sells",
        "selling",
        "seller",
        "sellers",
        "trade",
        "trades",
        "traded",
        "trading",
        "trader",
        "traders",
        "order",
        "orders",
        "ordered",
        "ordering",
        "authorize",
        "authorizes",
        "authorized",
        "authorizing",
        "authorise",
        "authorises",
        "authorised",
        "authorising",
        "authorization",
        "authorizations",
        "authorisation",
        "authorisations",
        "authority",
        "authorities",
        "permission",
        "permissions",
    }
)
CHINESE_TRADE_AUTHORITY_LEXEMES = (
    "\u4e70",
    "\u5356",
    "\u4ea4\u6613",
    "\u4e0b\u5355",
    "\u8ba2\u5355",
    "\u6743\u9650",
    "\u6388\u6743",
)
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "password",
        "passwd",
        "pwd",
        "cookie",
        "authorization",
        "secret",
        "credential",
        "access_key",
        "session",
        "session_id",
    }
)
PRIVATE_KEY_PREFIXES = (
    "account",
    "broker",
    "portfolio",
    "holding",
    "position",
    "share",
    "cost_basis",
    "costbasis",
    "risk_profile",
    "riskprofile",
    "personal_risk",
    "personalrisk",
    "raw_conversation",
    "rawconversation",
    "conversation",
    "chat_history",
)
HIDDEN_REASONING_KEYS = frozenset(
    {
        "reasoning",
        "chain_of_thought",
        "chainofthought",
        "hidden_thoughts",
        "hidden_reasoning",
        "thought_process",
        "analysis",
    }
)
TRADE_AUTHORITY_KEYS = frozenset(
    {
        "trade_authority",
        "execute_trade",
        "executetrade",
        "place_order",
        "placeorder",
        "submit_order",
        "submitorder",
        "broker_order",
    }
)


def normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def key_material_error(key: str) -> str | None:
    normalized = normalized_key(key)
    if normalized in SENSITIVE_KEYS or normalized.endswith("_token") or normalized.endswith("_secret"):
        return "sensitive key"
    if normalized in HIDDEN_REASONING_KEYS or "chain_of_thought" in normalized:
        return "hidden reasoning key"
    if normalized in TRADE_AUTHORITY_KEYS:
        return "trade authority key"
    if normalized.startswith(PRIVATE_KEY_PREFIXES):
        return "private key"
    return None


def has_valid_unicode(value: str) -> bool:
    return not any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _is_path_component_character(character: str) -> bool:
    return character.isalnum() or character in PATH_COMPONENT_PUNCTUATION


def _component_end(value: str, start: int) -> int:
    end = start
    while end < len(value) and _is_path_component_character(value[end]):
        end += 1
    return end


def _has_unc_host_and_share(value: str, start: int, separator: str) -> bool:
    host_end = _component_end(value, start)
    if host_end == start or host_end >= len(value) or value[host_end] != separator:
        return False
    share_start = host_end + 1
    return _component_end(value, share_start) > share_start


def _has_absolute_path_token(value: str) -> bool:
    """Scan a bounded public string for drive, UNC, or POSIX absolute path tokens."""

    for index, character in enumerate(value):
        if (
            character.isascii()
            and character.isalpha()
            and index + 2 < len(value)
            and value[index + 1] == ":"
            and value[index + 2] in {"/", "\\"}
        ):
            return True
        if value.startswith("\\\\", index):
            if value.startswith(("\\\\?\\", "\\\\.\\"), index):
                return True
            if _has_unc_host_and_share(value, index + 2, "\\"):
                return True
        if value.startswith("//", index) and _has_unc_host_and_share(value, index + 2, "/"):
            return True
        if character == "/" and not value.startswith("//", index):
            component_start = index + 1
            relative_ascii_prefix = (
                index > 0
                and value[index - 1].isascii()
                and _is_path_component_character(value[index - 1])
            )
            if (
                not relative_ascii_prefix
                and component_start < len(value)
                and _component_end(value, component_start) > component_start
            ):
                return True
    return False


def has_trade_authority_lexeme(value: str) -> bool:
    """Return true for any v1 trade-action or authority lexeme, without semantics."""

    return any(
        match.group(0).casefold() in ENGLISH_TRADE_AUTHORITY_LEXEMES
        for match in ASCII_WORD.finditer(value)
    ) or any(
        term in value for term in CHINESE_TRADE_AUTHORITY_LEXEMES
    )


def json_tree_error(
    value: object,
    location: str,
    *,
    max_depth: int = MAX_PUBLIC_DEPTH,
    max_items: int = MAX_PUBLIC_CONTAINER_ITEMS,
    max_containers: int = MAX_PUBLIC_CONTAINERS,
    max_string_length: int = MAX_PUBLIC_STRING_LENGTH,
    max_numeric_magnitude: int = MAX_PUBLIC_NUMERIC_MAGNITUDE,
) -> str | None:
    """Validate a decoded JSON tree iteratively with deterministic bounded errors."""

    stack: list[tuple[object, int]] = [(value, 0)]
    containers = 0
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            return f"{location} exceeds maximum depth"
        if isinstance(current, dict):
            containers += 1
            if containers > max_containers or len(current) > max_items:
                return f"{location} exceeds maximum container size"
            for key, child in current.items():
                if not isinstance(key, str) or len(key) > max_string_length or not has_valid_unicode(key):
                    return f"{location} contains invalid key"
                stack.append((child, depth + 1))
            continue
        if isinstance(current, list):
            containers += 1
            if containers > max_containers or len(current) > max_items:
                return f"{location} exceeds maximum container size"
            stack.extend((child, depth + 1) for child in current)
            continue
        if isinstance(current, str):
            if len(current) > max_string_length:
                return f"{location} exceeds maximum string length"
            if not has_valid_unicode(current):
                return f"{location} contains invalid unicode scalar"
            continue
        if isinstance(current, bool) or current is None:
            continue
        if isinstance(current, int):
            if abs(current) > max_numeric_magnitude:
                return f"{location} exceeds numeric bound"
            continue
        if isinstance(current, float):
            if not isfinite(current) or abs(current) > max_numeric_magnitude:
                return f"{location} exceeds numeric bound"
            continue
        return f"{location} contains a non-JSON value"
    return None


def public_material_error(value: object, *, reject_trade_lexemes: bool = True) -> str | None:
    """Reject material that cannot enter public or sanitized contracts."""

    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, child in current.items():
                if isinstance(key, str):
                    error = key_material_error(key)
                    if error:
                        return error
                stack.append(child)
            continue
        if isinstance(current, list):
            stack.extend(current)
            continue
        if isinstance(current, str):
            if any(pattern.search(current) for pattern in CREDENTIAL_VALUE_PATTERNS):
                return "credential-like value"
            if SENSITIVE_ASSIGNMENT.search(current):
                return "sensitive assignment"
            if URL_VALUE.search(current):
                return "URL"
            if _has_absolute_path_token(current):
                return "absolute path"
            if TRAVERSAL.search(current.replace("\\", "/")):
                return "path traversal"
            if PRIVATE_VALUE.search(current):
                return "private material"
            if reject_trade_lexemes and has_trade_authority_lexeme(current):
                return "trade authority lexeme"
    return None


def identifier_error(value: object, name: str) -> str | None:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        return f"{name} must be a bounded ASCII identifier"
    return None


def reference_error(value: object, name: str) -> str | None:
    if not isinstance(value, str) or not REFERENCE.fullmatch(value):
        return f"{name} must be a bounded relative reference"
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or "//" in value:
        return f"{name} must be a bounded relative reference"
    if _has_absolute_path_token(value) or TRAVERSAL.search(value):
        return f"{name} must be a bounded relative reference"
    return None


def read_bounded_bytes(path: Path, limit: int, label: str) -> bytes:
    """Open once and return at most one bounded file snapshot."""

    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(limit + 1)
    except OSError as exc:
        raise ValueError(f"{label} cannot be read") from exc
    if len(raw) > limit:
        raise ValueError(f"{label} exceeds maximum size")
    return raw
