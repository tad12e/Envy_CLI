from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import click


DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
DEFAULT_PROVIDER = "anthropic"

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

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


@dataclass(frozen=True)
class AgenticScanConfig:
    root: Path
    env_file: Path
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    max_tool_loops: int = 30
    max_files_listed: int = 500


def _safe_resolve_under_root(root: Path, user_path: str) -> Path:
    """Resolve `user_path` under `root` and block escaping via '..' or absolute paths."""
    candidate = Path(user_path)
    if candidate.is_absolute():
        resolved = candidate
    else:
        resolved = (root / candidate)

    try:
        resolved = resolved.resolve()
        root_resolved = root.resolve()
    except OSError:
        resolved = resolved.absolute()
        root_resolved = root.absolute()

    # Ensure the file is under the root
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {user_path}") from exc

    return resolved


def _iter_files(root: Path, max_results: int) -> Iterable[Path]:
    count = 0
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path
            count += 1
            if count >= max_results:
                return


def tool_list_files(root: Path, relative_glob: Optional[str], max_results: int) -> str:
    if relative_glob is None or not str(relative_glob).strip():
        files = list(_iter_files(root, max_results=max_results))
    else:
        # Constrain glob to root
        pattern = str(relative_glob)
        files = []
        for path in root.rglob(pattern):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file():
                files.append(path)
                if len(files) >= max_results:
                    break

    rel = []
    for path in sorted(files):
        try:
            rel.append(str(path.resolve().relative_to(root.resolve())).replace("\\", "/"))
        except Exception:
            rel.append(str(path))

    return json.dumps({"root": str(root), "count": len(rel), "files": rel}, indent=2)


def tool_read_file(root: Path, path: str, start_line: int, end_line: int) -> str:
    resolved = _safe_resolve_under_root(root, path)

    if not resolved.exists() or not resolved.is_file():
        return json.dumps({"path": path, "error": "File not found"}, indent=2)

    try:
        text = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # pragma: no cover
            return json.dumps({"path": path, "error": f"Unable to read file: {exc}"}, indent=2)
    except Exception as exc:
        return json.dumps({"path": path, "error": f"Unable to read file: {exc}"}, indent=2)

    lines = text.splitlines()
    total = len(lines)
    start = max(1, int(start_line))
    end = max(start, int(end_line))
    start = min(start, total if total > 0 else 1)
    end = min(end, total if total > 0 else 1)

    snippet = lines[start - 1 : end]

    return json.dumps(
        {
            "path": path,
            "resolved_path": str(resolved),
            "total_lines": total,
            "start_line": start,
            "end_line": end,
            "text": "\n".join(snippet),
        },
        indent=2,
    )


def tool_search_in_file(root: Path, path: str, query: str, is_regex: bool, max_results: int) -> str:
    resolved = _safe_resolve_under_root(root, path)
    if not resolved.exists() or not resolved.is_file():
        return json.dumps({"path": path, "error": "File not found"}, indent=2)

    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return json.dumps({"path": path, "error": f"Unable to read file: {exc}"}, indent=2)

    results: List[Dict[str, Any]] = []

    if is_regex:
        try:
            pattern = re.compile(query)
        except re.error as exc:
            return json.dumps({"path": path, "error": f"Invalid regex: {exc}"}, indent=2)

        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                results.append({"line": i, "text": line})
                if len(results) >= max_results:
                    break
    else:
        needle = query
        for i, line in enumerate(text.splitlines(), start=1):
            if needle in line:
                results.append({"line": i, "text": line})
                if len(results) >= max_results:
                    break

    return json.dumps({"path": path, "query": query, "count": len(results), "results": results}, indent=2)


def _tools_schema() -> List[Dict[str, Any]]:
    return [
        {
            "name": "list_files",
            "description": "List files under the project root. Optionally filter via a relative glob.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "relative_glob": {"type": ["string", "null"], "description": "Relative glob like 'src/**/*.py'"},
                    "max_results": {"type": "integer", "description": "Max number of files", "default": 200},
                },
                "required": [],
            },
        },
        {
            "name": "read_file",
            "description": "Read a file (by relative path) with a line range.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path from project root"},
                    "start_line": {"type": "integer", "default": 1},
                    "end_line": {"type": "integer", "default": 200},
                },
                "required": ["path"],
            },
        },
        {
            "name": "search_in_file",
            "description": "Search for a substring or regex inside a file.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path from project root"},
                    "query": {"type": "string"},
                    "is_regex": {"type": "boolean", "default": False},
                    "max_results": {"type": "integer", "default": 50},
                },
                "required": ["path", "query"],
            },
        },
    ]


def _tools_schema_openai() -> List[Dict[str, Any]]:
    """OpenAI tool schema format (function tools)."""
    tools = []
    for tool in _tools_schema():
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
        )
    return tools


def _system_prompt() -> str:
    return (
        "You are a senior security engineer auditing a software repository for environment-variable hygiene and leaked secrets.\n"
        "You MUST autonomously explore the repo using the provided tools until you have enough evidence.\n\n"
        "Your goals:\n"
        "1) Find hardcoded secrets in code (API keys, tokens, passwords, private keys).\n"
        "2) Find environment variables used in code but missing from the env file.\n"
        "3) Find variables in the env file that are empty or placeholder values (e.g. 'changeme', 'your_api_key', '<...>').\n"
        "4) Determine whether the env file is ignored by git (check .gitignore).\n"
        "5) Suggest .env additions (keys with brief comments).\n\n"
        "Rules:\n"
        "- Use ONLY these tools: list_files, read_file, search_in_file.\n"
        "- Prefer targeted reads/searches (don’t read huge files unless needed).\n"
        "- When you report hardcoded secrets, include file path and 1-based line number.\n"
        "- If a file cannot be read (error returned by tool), continue gracefully.\n\n"
        "Final output MUST be valid JSON (no markdown) with these keys:\n"
        "hardcoded_secrets: array of {path, line, evidence, severity}\n"
        "missing_env_vars: array of {name, evidence}\n"
        "env_placeholders: array of {name, value, issue}\n"
        "gitignore_status: {env_file, ignored: bool, evidence}\n"
        "suggested_env_additions: array of {name, comment}\n"
        "notes: array of strings\n"
    )


def _execute_tool(root: Path, config: AgenticScanConfig, tool_name: str, tool_input: Dict[str, Any]) -> str:
    try:
        if tool_name == "list_files":
            click.echo(click.style("[tool] list_files", fg="cyan"))
            return tool_list_files(
                root=root,
                relative_glob=tool_input.get("relative_glob"),
                max_results=int(tool_input.get("max_results", config.max_files_listed)),
            )
        if tool_name == "read_file":
            path = str(tool_input.get("path"))
            click.echo(click.style(f"[tool] read_file: {path}", fg="cyan"))
            return tool_read_file(
                root=root,
                path=path,
                start_line=int(tool_input.get("start_line", 1)),
                end_line=int(tool_input.get("end_line", 200)),
            )
        if tool_name == "search_in_file":
            path = str(tool_input.get("path"))
            click.echo(click.style(f"[tool] search_in_file: {path}", fg="cyan"))
            return tool_search_in_file(
                root=root,
                path=path,
                query=str(tool_input.get("query", "")),
                is_regex=bool(tool_input.get("is_regex", False)),
                max_results=int(tool_input.get("max_results", 50)),
            )
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as exc:
        return json.dumps({"error": f"Tool execution failed: {exc}"})


def _run_agentic_scan_anthropic(config: AgenticScanConfig) -> Dict[str, Any]:
    root = config.root
    if not root.exists() or not root.is_dir():
        raise click.ClickException(f"Root directory does not exist: {root}")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise click.ClickException(
            "Missing ANTHROPIC_API_KEY. Set it in your environment before running `envy agentic-scan`."
        )

    try:
        import anthropic  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise click.ClickException(
            "Missing dependency 'anthropic'. Install it (e.g. `pip install anthropic`)."
        ) from exc

    client = anthropic.Anthropic(api_key=api_key)

    messages: List[Dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                f"Scan this repository.\nProject root: {root}\nEnv file (relative): {config.env_file}\n"
                "Start by listing key files and checking the env file and .gitignore."
            ),
        }
    ]

    tools = _tools_schema()

    loops = 0
    while True:
        loops += 1
        if loops > config.max_tool_loops:
            raise click.ClickException("Agentic scan exceeded max tool loops; try increasing --max-loops.")

        resp = client.messages.create(
            model=config.model,
            max_tokens=2000,
            system=_system_prompt(),
            tools=tools,
            messages=messages,
        )

        # If the model requests tool use, execute those tool calls and continue.
        if getattr(resp, "stop_reason", None) == "tool_use":
            tool_results_content: List[Dict[str, Any]] = []

            for block in resp.content:
                if getattr(block, "type", None) != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input or {}

                payload = _execute_tool(root=root, config=config, tool_name=tool_name, tool_input=tool_input)

                tool_results_content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": payload,
                    }
                )

            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": tool_results_content})
            continue

        # Otherwise, we expect a final JSON report.
        final_text_parts: List[str] = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                final_text_parts.append(block.text)

        final_text = "\n".join(final_text_parts).strip()
        try:
            return json.loads(final_text) if final_text else {}
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"Model did not return valid JSON: {exc}\n\nRaw output:\n{final_text}")


def _run_agentic_scan_openai(config: AgenticScanConfig) -> Dict[str, Any]:
    return _run_agentic_scan_openai_compatible(
        config=config,
        api_key_env="OPENAI_API_KEY",
        provider_name="openai",
        base_url=os.getenv("OPENAI_BASE_URL"),
        missing_key_help="Missing OPENAI_API_KEY. Set it in your environment before running `envy agentic-scan --provider openai`.",
    )


def _run_agentic_scan_deepseek(config: AgenticScanConfig) -> Dict[str, Any]:
    base_url = os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL
    return _run_agentic_scan_openai_compatible(
        config=config,
        api_key_env="DEEPSEEK_API_KEY",
        provider_name="deepseek",
        base_url=base_url,
        missing_key_help=(
            "Missing DEEPSEEK_API_KEY. Set it in your environment before running `envy agentic-scan --provider deepseek`."
        ),
    )


def _run_agentic_scan_openai_compatible(
    *,
    config: AgenticScanConfig,
    api_key_env: str,
    provider_name: str,
    base_url: Optional[str],
    missing_key_help: str,
) -> Dict[str, Any]:
    root = config.root
    if not root.exists() or not root.is_dir():
        raise click.ClickException(f"Root directory does not exist: {root}")

    api_key = os.getenv(api_key_env)
    if not api_key:
        raise click.ClickException(missing_key_help)

    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise click.ClickException(
            f"Missing dependency 'openai'. Install it (e.g. `pip install openai`) to use provider '{provider_name}'."
        ) from exc

    # The OpenAI Python SDK supports OpenAI-compatible endpoints via base_url.
    if base_url:
        client = OpenAI(api_key=api_key, base_url=base_url)
    else:
        client = OpenAI(api_key=api_key)

    system_prompt = _system_prompt()
    user_prompt = (
        f"Scan this repository.\nProject root: {root}\nEnv file (relative): {config.env_file}\n"
        "Start by listing key files and checking the env file and .gitignore."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    tools = _tools_schema_openai()

    loops = 0
    while True:
        loops += 1
        if loops > config.max_tool_loops:
            raise click.ClickException("Agentic scan exceeded max tool loops; try increasing --max-loops.")

        resp = client.chat.completions.create(
            model=config.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        choice = resp.choices[0]
        finish = getattr(choice, "finish_reason", None)
        msg = choice.message

        if finish == "tool_calls" and getattr(msg, "tool_calls", None):
            # Append assistant tool-call request
            assistant_message: Dict[str, Any] = {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
            messages.append(assistant_message)

            # Execute tools and append tool results
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    tool_input = {}

                payload = _execute_tool(root=root, config=config, tool_name=tool_name, tool_input=tool_input)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tool_name,
                        "content": payload,
                    }
                )
            continue

        final_text = (msg.content or "").strip()
        try:
            return json.loads(final_text) if final_text else {}
        except json.JSONDecodeError as exc:
            raise click.ClickException(f"Model did not return valid JSON: {exc}\n\nRaw output:\n{final_text}")


def run_agentic_scan(config: AgenticScanConfig) -> Dict[str, Any]:
    provider = (config.provider or DEFAULT_PROVIDER).strip().lower()
    if provider == "anthropic":
        return _run_agentic_scan_anthropic(config)
    if provider == "openai":
        return _run_agentic_scan_openai(config)
    if provider == "deepseek":
        return _run_agentic_scan_deepseek(config)
    raise click.ClickException(
        f"Unknown provider: {config.provider}. Use 'anthropic', 'openai', or 'deepseek'."
    )


def print_colored_report(report: Dict[str, Any]) -> None:
    def header(text: str) -> None:
        click.echo(click.style(text, bold=True, fg="white"))

    def good(text: str) -> None:
        click.echo(click.style(text, fg="green"))

    def warn(text: str) -> None:
        click.echo(click.style(text, fg="yellow"))

    def bad(text: str) -> None:
        click.echo(click.style(text, fg="red"))

    hardcoded = report.get("hardcoded_secrets", []) or []
    missing = report.get("missing_env_vars", []) or []
    placeholders = report.get("env_placeholders", []) or []
    gitignore = report.get("gitignore_status", {}) or {}
    suggestions = report.get("suggested_env_additions", []) or []
    notes = report.get("notes", []) or []

    header("Agentic Scan Report")

    header("\nHardcoded secrets")
    if not hardcoded:
        good("- None found")
    else:
        for item in hardcoded:
            path = item.get("path", "?")
            line = item.get("line", "?")
            severity = str(item.get("severity", "high")).lower()
            evidence = str(item.get("evidence", "")).strip()
            printer = bad if severity in {"high", "critical"} else warn
            printer(f"- {path}:{line} [{severity}] {evidence}")

    header("\nVars used in code but missing from env")
    if not missing:
        good("- None found")
    else:
        for item in missing:
            warn(f"- {item.get('name', '?')}: {item.get('evidence', '').strip()}")

    header("\nEnv placeholders / empty values")
    if not placeholders:
        good("- None found")
    else:
        for item in placeholders:
            warn(f"- {item.get('name', '?')}={item.get('value', '')} ({item.get('issue', '')})")

    header("\n.gitignore status")
    ignored = bool(gitignore.get("ignored", False))
    env_file = gitignore.get("env_file", ".env")
    evidence = gitignore.get("evidence", "")
    if ignored:
        good(f"- {env_file} appears ignored")
    else:
        warn(f"- {env_file} does NOT appear ignored")
    if evidence:
        click.echo(click.style(f"  evidence: {evidence}", fg="bright_black"))

    header("\nSuggested .env additions")
    if not suggestions:
        good("- None")
    else:
        for item in suggestions:
            name = item.get("name", "?")
            comment = item.get("comment", "").strip()
            click.echo(click.style(f"- {name}  # {comment}", fg="cyan"))

    if notes:
        header("\nNotes")
        for note in notes:
            click.echo(click.style(f"- {note}", fg="bright_black"))
