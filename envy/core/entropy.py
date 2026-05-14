import math
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Set


TOKEN_RE = re.compile(r"[A-Za-z0-9_\-+/=]{20,}")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<name>[A-Z0-9_]*(?:SECRET|PASSWORD|TOKEN|PRIVATE|API_KEY|ACCESS_KEY|CREDENTIAL)[A-Z0-9_]*)"
    r"\s*[:=]\s*['\"]?(?P<value>[^'\"\s#]+)",
    re.IGNORECASE,
)
KNOWN_SECRET_PATTERNS = {
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "Private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
PLACEHOLDER_VALUES = {
    "",
    "changeme",
    "change_me",
    "example",
    "placeholder",
    "secret",
    "supersecretvalue",
    "test",
    "todo",
    "your_api_key",
    "your-secret",
}
TEXT_EXTENSIONS = {
    ".env",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".md",
    ".sh",
}


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    probabilities = [value.count(char) / len(value) for char in set(value)]
    return -sum(prob * math.log2(prob) for prob in probabilities)


def _looks_like_placeholder(value: str) -> bool:
    cleaned = value.strip().strip("'\"").lower()
    return (
        cleaned in PLACEHOLDER_VALUES
        or cleaned.startswith("your_")
        or cleaned.startswith("<")
        or cleaned.startswith("re.")
        or cleaned.startswith("match.")
        or cleaned == "match"
        or "{" in cleaned
        or "(" in cleaned
    )


def _looks_like_scanner_constant(name: str) -> bool:
    upper_name = name.upper()
    return upper_name.endswith("_RE") or "PATTERN" in upper_name


def _read_gitignore_entries() -> Set[str]:
    path = Path(".gitignore")
    if not path.exists():
        return set()

    entries: Set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        entries.add(text.rstrip("/"))
    return entries


def _is_ignored(path: Path, ignored_entries: Set[str]) -> bool:
    parts = set(path.parts)
    for entry in ignored_entries:
        if entry in parts or str(path).startswith(entry):
            return True
    return False


def _list_files(staged_only: bool) -> List[Path]:
    if staged_only:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]

    result = subprocess.run(
        ["git", "ls-files"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def scan_files_for_entropy(staged_only: bool, entropy_threshold: float) -> List[Dict[str, object]]:
    ignored_entries = _read_gitignore_entries()
    findings: List[Dict[str, object]] = []
    for path in _list_files(staged_only):
        if not path.exists() or _is_ignored(path, ignored_entries):
            continue
        if path.suffix and path.suffix.lower() not in TEXT_EXTENSIONS:
            continue

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue

        for index, line in enumerate(lines, start=1):
            for label, pattern in KNOWN_SECRET_PATTERNS.items():
                for match in pattern.findall(line):
                    token = match if isinstance(match, str) else match[0]
                    findings.append(
                        {
                            "path": str(path),
                            "line": index,
                            "token": token,
                            "entropy": shannon_entropy(token),
                            "reason": label,
                        }
                    )

            for match in SECRET_ASSIGNMENT_RE.finditer(line):
                if _looks_like_scanner_constant(match.group("name")):
                    continue
                token = match.group("value")
                if _looks_like_placeholder(token):
                    continue
                findings.append(
                    {
                        "path": str(path),
                        "line": index,
                        "token": token,
                        "entropy": shannon_entropy(token),
                        "reason": f"secret-looking assignment to {match.group('name')}",
                    }
                )

            for token in TOKEN_RE.findall(line):
                entropy = shannon_entropy(token)
                if entropy >= entropy_threshold:
                    findings.append(
                        {
                            "path": str(path),
                            "line": index,
                            "token": token,
                            "entropy": entropy,
                            "reason": "high entropy token",
                        }
                    )
    return findings


def install_pre_commit_hook(entropy_threshold: float) -> Path:
    hook_path = Path(".git") / "hooks" / "pre-commit"
    hook_path.parent.mkdir(parents=True, exist_ok=True)

    script = (
        "#!/bin/sh\n"
        f"envy scan --staged --threshold {entropy_threshold}\n"
        "if [ $? -ne 0 ]; then\n"
        "  echo 'Envy blocked this commit due to potential secret leaks.'\n"
        "  exit 1\n"
        "fi\n"
    )
    hook_path.write_text(script, encoding="utf-8")

    try:
        hook_path.chmod(0o755)
    except OSError:
        # chmod may not be supported on all Windows setups.
        pass

    return hook_path
