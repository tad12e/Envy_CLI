import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from dotenv import dotenv_values


SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rb",
    ".php",
    ".java",
    ".cs",
    ".rs",
    ".sh",
}

PROJECT_ROOT_MARKERS = {
    ".git",
    "pyproject.toml",
    "Envy.toml",
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "requirements.txt",
    "Pipfile",
    "poetry.lock",
    "go.mod",
    "Cargo.toml",
}
SKIP_DIRS = {
    ".git",
    ".venv",
    ".venv-wsl",
    ".venv-window",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "vendor",
}
SENSITIVE_KEY_PATTERN = re.compile(r"(SECRET|PASSWORD|TOKEN|PRIVATE|API_KEY|ACCESS_KEY|CREDENTIAL)", re.IGNORECASE)
ENV_NAME_RE = r"[A-Z][A-Z0-9_]{1,}"
ENV_ACCESS_PATTERNS = [
    re.compile(r"os\.getenv\(\s*['\"](?P<name>" + ENV_NAME_RE + r")['\"](?:\s*,\s*(?P<default>[^)\n]+))?"),
    re.compile(r"os\.environ\.get\(\s*['\"](?P<name>" + ENV_NAME_RE + r")['\"](?:\s*,\s*(?P<default>[^)\n]+))?"),
    re.compile(r"os\.environ\[\s*['\"](?P<name>" + ENV_NAME_RE + r")['\"]\s*\]"),
    re.compile(r"process\.env\.(?P<name>" + ENV_NAME_RE + r")\b"),
    re.compile(r"process\.env\[\s*['\"](?P<name>" + ENV_NAME_RE + r")['\"]\s*\]"),
]


def _iter_source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS:
            yield path


def find_project_root(start: Path) -> Path:
    """Walk upward from `start` to find a likely project root.

    Falls back to the provided directory if no markers are found.
    """
    start_path = start
    if start_path.exists() and start_path.is_file():
        start_path = start_path.parent

    try:
        start_path = start_path.resolve()
    except OSError:
        start_path = start_path.absolute()

    for candidate in (start_path, *start_path.parents):
        for marker in PROJECT_ROOT_MARKERS:
            marker_path = candidate / marker
            if marker == ".git":
                if marker_path.exists():
                    return candidate
            elif marker_path.is_file():
                return candidate

    return start_path


def _clean_default(raw_default: Optional[str]) -> Any:
    if raw_default is None:
        return None

    text = raw_default.strip().rstrip(",")
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    if text.lower() in {"none", "null"}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return None


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "false", "yes", "no", "1", "0"}:
            return "bool"
        try:
            int(value)
            return "int"
        except ValueError:
            pass
        try:
            float(value)
            return "float"
        except ValueError:
            pass
    return "str"


def _is_sensitive(name: str) -> bool:
    return bool(SENSITIVE_KEY_PATTERN.search(name))


def infer_schema(root: Path, env_file: Optional[Path] = None) -> Dict[str, Any]:
    variables: Dict[str, Dict[str, Any]] = {}
    sources: Dict[str, Set[str]] = {}

    for path in _iter_source_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for pattern in ENV_ACCESS_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group("name")
                default = _clean_default(match.groupdict().get("default"))
                current = variables.setdefault(
                    name,
                    {
                        "type": _infer_type(default),
                        "required": default is None,
                        "description": f"Inferred from code reference: {name}.",
                        "sensitive": _is_sensitive(name),
                    },
                )
                if default is not None:
                    current["required"] = False
                    current["default"] = default
                    current["type"] = _infer_type(default)
                sources.setdefault(name, set()).add(str(path))

    if env_file and env_file.exists():
        for name, value in dotenv_values(env_file).items():
            if value is None:
                continue
            current = variables.setdefault(
                name,
                {
                    "description": f"Inferred from {env_file}.",
                    "required": True,
                    "sensitive": _is_sensitive(name),
                },
            )
            current["type"] = _infer_type(value)
            if not current.get("sensitive", False):
                current.setdefault("default", value)
                current["required"] = False

    for name, spec in variables.items():
        if name in sources:
            source_list = ", ".join(sorted(sources[name]))
            spec["description"] = f"Inferred from code usage in {source_list}."

    return {"variables": dict(sorted(variables.items()))}


def write_inferred_schema(root: Path, env_file: Optional[Path], output: Path) -> int:
    import json

    schema = infer_schema(root=root, env_file=env_file)
    output.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    return len(schema["variables"])
