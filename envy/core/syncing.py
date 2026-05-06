import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from dotenv import dotenv_values


SENSITIVE_KEY_PATTERN = re.compile(r"(SECRET|PASSWORD|TOKEN|PRIVATE|API_KEY|ACCESS_KEY)", re.IGNORECASE)


def _resolve_key(explicit_key: Optional[str]) -> str:
    key = explicit_key or os.getenv("ENVY_SYNC_KEY")
    if not key:
        raise ValueError("Missing encryption key. Use --key or ENVY_SYNC_KEY.")
    return key


def _is_sensitive(name: str, schema: Optional[Dict[str, Any]]) -> bool:
    if SENSITIVE_KEY_PATTERN.search(name):
        return True
    if not schema:
        return False

    spec = schema.get("variables", {}).get(name, {})
    return bool(spec.get("sensitive", False))


def _read_env(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    raw = dotenv_values(path)
    return {key: value for key, value in raw.items() if value is not None}


def push_sync_file(env_file: Path, output_file: Path, key: Optional[str], schema: Optional[Dict[str, Any]]) -> int:
    env_values = _read_env(env_file)
    if not env_values:
        raise ValueError(f"No variables found in {env_file}")

    sync_values = {k: v for k, v in env_values.items() if not _is_sensitive(k, schema)}
    if not sync_values:
        raise ValueError("No non-sensitive variables available to sync.")

    cipher = Fernet(_resolve_key(key).encode("utf-8"))
    payload = json.dumps(sync_values, sort_keys=True).encode("utf-8")
    output_file.write_bytes(cipher.encrypt(payload))
    return len(sync_values)


def pull_sync_file(input_file: Path, env_file: Path, key: Optional[str], overwrite: bool) -> int:
    if not input_file.exists():
        raise FileNotFoundError(f"Missing sync file: {input_file}")

    cipher = Fernet(_resolve_key(key).encode("utf-8"))
    decrypted = cipher.decrypt(input_file.read_bytes())
    incoming = json.loads(decrypted.decode("utf-8"))
    if not isinstance(incoming, dict):
        raise ValueError("Invalid sync payload.")

    current = _read_env(env_file)
    merged_count = 0
    for key_name, value in incoming.items():
        if overwrite or key_name not in current:
            current[key_name] = str(value)
            merged_count += 1

    lines = [f"{name}={current[name]}" for name in sorted(current.keys())]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return merged_count