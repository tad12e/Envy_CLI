from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from envy.core.docs import generate_readme_env
from envy.core.entropy import install_pre_commit_hook, scan_files_for_entropy
from envy.core.infer import find_project_root, infer_schema, write_inferred_schema
from envy.core.schema import load_schema_definition, validate_env_file
from envy.core.syncing import pull_sync_file, push_sync_file

console = Console()
cli = typer.Typer(help="Envy: A suite of tools to manage environment variables securely.")
sync_app = typer.Typer(help="Share non-sensitive environment config with your team.")
cli.add_typer(sync_app, name="sync")


@cli.command("check")
def check_command(
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Path to .env file."),
    schema_file: Optional[Path] = typer.Option(
        None,
        "--schema-file",
        help="Path to schema file (defaults: envy.schema.json or .env.template).",
    ),
    infer: bool = typer.Option(False, "--infer", help="Infer schema from code and env file instead of loading one."),
) -> None:
    """Validate .env against a schema file or template."""
    root = find_project_root(Path.cwd())
    resolved_schema = infer_schema(root, env_file) if infer else load_schema_definition(schema_file)
    report = validate_env_file(env_file, resolved_schema)

    if report["ok"]:
        console.print("[green]Environment validation passed.[/green]")
        return

    console.print("[red]Environment validation failed.[/red]")
    for issue in report["issues"]:
        console.print(f"- {issue}")
    raise typer.Exit(code=1)


@cli.command("docs")
def docs_command(
    output: Path = typer.Option(Path("README_ENV.md"), "--output", help="Markdown output file."),
    schema_file: Optional[Path] = typer.Option(
        None,
        "--schema-file",
        help="Path to schema file (defaults: envy.schema.json or .env.template).",
    ),
) -> None:
    """Generate README_ENV.md from the schema."""
    schema = load_schema_definition(schema_file)
    generate_readme_env(schema, output)
    console.print(f"[green]Wrote docs to {output}[/green]")


@cli.command("infer-schema")
def infer_schema_command(
    root: Optional[Path] = typer.Option(None, "--root", help="Project root to scan for env usage (defaults to auto-detected root)."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Optional .env file to inspect."),
    output: Path = typer.Option(Path("envy.schema.json"), "--output", help="Schema output file."),
) -> None:
    """Generate a schema from env usage in code and values in an env file."""
    resolved_root = find_project_root(Path.cwd()) if root is None else root
    count = write_inferred_schema(root=resolved_root, env_file=env_file, output=output)
    console.print(f"[green]Inferred {count} variables into {output}[/green]")


@cli.command("infer")
def infer_schema_alias_command(
    root: Optional[Path] = typer.Option(None, "--root", help="Project root to scan for env usage (defaults to auto-detected root)."),
    env_file: Optional[Path] = typer.Option(Path(".env"), "--env-file", help="Optional .env file to inspect."),
    output: Path = typer.Option(Path("envy.schema.json"), "--output", help="Schema output file."),
) -> None:
    """Alias for `infer-schema`."""
    resolved_root = find_project_root(Path.cwd()) if root is None else root
    count = write_inferred_schema(root=resolved_root, env_file=env_file, output=output)
    console.print(f"[green]Inferred {count} variables into {output}[/green]")


@cli.command("scan")
def scan_command(
    staged: bool = typer.Option(False, "--staged", help="Scan only staged files."),
    threshold: float = typer.Option(4.3, "--threshold", help="Entropy threshold for alerts."),
) -> None:
    """Scan files for likely leaked secrets using Shannon entropy."""
    findings = scan_files_for_entropy(staged_only=staged, entropy_threshold=threshold)
    if not findings:
        console.print("[green]No high-entropy findings detected.[/green]")
        return

    console.print("[red]Potential secret leaks detected:[/red]")
    for finding in findings:
        console.print(
            f"- {finding['path']}:{finding['line']} {finding['reason']} entropy={finding['entropy']:.2f} token={finding['token'][:8]}..."
        )
    raise typer.Exit(code=1)


@cli.command("install-hook")
def install_hook_command(
    threshold: float = typer.Option(4.3, "--threshold", help="Entropy threshold for the hook."),
) -> None:
    """Install a pre-commit hook that blocks suspicious secrets."""
    hook_path = install_pre_commit_hook(entropy_threshold=threshold)
    console.print(f"[green]Installed pre-commit hook at {hook_path}[/green]")


@sync_app.command("push")
def sync_push_command(
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Path to local .env file."),
    output_file: Path = typer.Option(Path(".envy.sync"), "--output-file", help="Encrypted sync file."),
    key: Optional[str] = typer.Option(None, "--key", help="Fernet key (or use ENVY_SYNC_KEY)."),
    schema_file: Optional[Path] = typer.Option(None, "--schema-file", help="Optional schema for sensitivity rules."),
) -> None:
    """Encrypt and push non-sensitive vars into .envy.sync."""
    schema = load_schema_definition(schema_file, required=False)
    count = push_sync_file(env_file=env_file, output_file=output_file, key=key, schema=schema)
    console.print(f"[green]Encrypted {count} variables into {output_file}[/green]")


@sync_app.command("pull")
def sync_pull_command(
    input_file: Path = typer.Option(Path(".envy.sync"), "--input-file", help="Encrypted sync file."),
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Path to local .env file."),
    key: Optional[str] = typer.Option(None, "--key", help="Fernet key (or use ENVY_SYNC_KEY)."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing local values."),
) -> None:
    """Decrypt and merge .envy.sync into local .env."""
    merged = pull_sync_file(input_file=input_file, env_file=env_file, key=key, overwrite=overwrite)
    console.print(f"[green]Merged {merged} variables into {env_file}[/green]")


if __name__ == "__main__":
    cli()
