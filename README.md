# Envy

Envy is a CLI for managing environment variables safely:

- Validate a `.env` file against a schema/template (or infer one from code)
- Generate documentation for environment variables
- Scan for likely secret leaks (entropy-based)
- Encrypt and share _non-sensitive_ environment config with your team
- Run an optional “agentic” security audit using an LLM with tool-calling

This repository is packaged as a Python project (see `pyproject.toml`).

---

## Installation

### Install from PyPI (recommended)

Once published, install the package name from `pyproject.toml`:

```bash
pip install envy-cli
```

After install, you should have the `envy` command:

```bash
envy --help
```

### Install with pipx (best for CLIs)

```bash
pipx install envy-cli
envy --help
```

### Install in a virtual environment

Linux/macOS/WSL:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install envy-cli
envy --help
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install envy-cli
envy --help
```

### Run without installing (for repo development)

If you are running directly from a clone of this repo:

```bash
python -m envy.main --help
```

---

## Optional project config: `Envy.toml`

You may add an `Envy.toml` file at your project root.

Current behavior:

- Envy treats `Envy.toml` as a **project root marker** (it helps `--root` auto-detection).
- CLI flags still take precedence over anything in `Envy.toml`.

Example `Envy.toml` (from this repo):

```toml
[envy]
env_file = ".env"
schema_file = "envy.schema.json"
docs_output = "README_ENV.md"
sync_output_file = ".envy.sync"
entropy_threshold = 4.3
```

---

## Quickstart

1. Validate your `.env`:

```bash
envy check --env-file .env
```

2. If you don’t have a schema yet, infer one:

```bash
envy infer-schema --env-file .env --output envy.schema.json
```

3. Generate docs for your team:

```bash
envy docs --schema-file envy.schema.json --output README_ENV.md
```

---

## Global help

To see all commands:

```bash
envy --help
```

To see help for a specific command:

```bash
envy check --help
envy sync --help
envy sync push --help
```

---

## Command reference

Below is a detailed reference for every command and every flag currently exposed by the CLI.

### `envy check`

Validate a `.env` file against a schema definition.

What it does:

- Loads a schema from `--schema-file` (or defaults like `envy.schema.json` / `.env.template`)
- OR, if `--infer` is set, infers schema from your codebase + env file
- Produces a pass/fail report

Flags:

- `--env-file PATH` (default: `.env`)
  - The env file to validate
- `--schema-file PATH` (optional)
  - Schema file to use (if omitted and `--infer` is not set, Envy attempts defaults)
- `--infer` (default: false)
  - Infer the schema from code/env instead of loading a schema file

Examples:

```bash
# Validate the default .env using default schema resolution
envy check

# Validate a specific env file
envy check --env-file .env.local

# Validate against an explicit schema file
envy check --env-file .env --schema-file envy.schema.json

# Infer schema from code, then validate
envy check --infer --env-file .env
```

---

### `envy docs`

Generate documentation (Markdown) from a schema.

Flags:

- `--output PATH` (default: `README_ENV.md`)
  - Where to write the generated documentation
- `--schema-file PATH` (optional)
  - Schema file to read (if omitted, Envy attempts defaults)

Examples:

```bash
# Generate docs using default schema resolution
envy docs

# Generate docs from an explicit schema file
envy docs --schema-file envy.schema.json

# Write to a custom location
envy docs --schema-file envy.schema.json --output docs/ENVIRONMENT.md
```

---

### `envy infer-schema`

Infer an environment-variable schema by scanning your repository for env-var usage patterns (and optionally inspecting values in an env file).

Flags:

- `--root PATH` (optional)
  - Project root to scan
  - If omitted, Envy attempts to auto-detect a project root from the current working directory
- `--env-file PATH` (default: `.env`)
  - Optional env file to read values from (helps infer types/required-ness)
- `--output PATH` (default: `envy.schema.json`)
  - Where to write the inferred schema

Examples:

```bash
# Infer schema from the current project
envy infer-schema

# Infer schema using a specific env file
envy infer-schema --env-file .env

# Infer schema for a different root directory
envy infer-schema --root .. --env-file .env --output envy.schema.json
```

---

### `envy infer`

Alias for `envy infer-schema`.

Examples:

```bash
envy infer --env-file .env --output envy.schema.json
```

---

### `envy scan`

Scan files for likely leaked secrets using Shannon entropy (high-entropy tokens often correlate with keys/tokens).

Flags:

- `--staged` (default: false)
  - Only scan staged git changes (useful before commit)
- `--threshold FLOAT` (default: `4.3`)
  - Higher threshold = fewer findings (more strict about what counts as “suspicious”)
  - Lower threshold = more findings

Examples:

```bash
# Scan the repository
envy scan

# Scan only staged changes
envy scan --staged

# Make the scan stricter
envy scan --threshold 4.6

# Make the scan more sensitive
envy scan --threshold 4.0
```

---

### `envy install-hook`

Install a pre-commit hook that runs Envy’s entropy scan and blocks commits that look like secret leaks.

Flags:

- `--threshold FLOAT` (default: `4.3`)
  - Same meaning as `envy scan --threshold`

Examples:

```bash
# Install the hook with defaults
envy install-hook

# Install with a stricter threshold
envy install-hook --threshold 4.6
```

---

### `envy agentic-scan`

Run an LLM-powered “agentic” security scan.

What it does:

- Sends a system prompt describing a security audit task
- Lets the model explore your repository using tool-calling:
  - `list_files` (bounded)
  - `read_file` (bounded line ranges)
  - `search_in_file` (substring or regex)
- Loops until the model returns a final JSON report

Important notes:

- This command can make paid API calls depending on your provider
- Envy does NOT ship any default API keys. You must provide your own provider API key.
- Output is expected to be valid JSON; if the model returns non-JSON, the command will fail

Safe testing tip:

- If you don’t want to use a real `.env` yet, you can point `--env-file` to `.env.example`.

Setting API keys:

- Temporary (only for the current terminal session): set the env var, run the command.
- Persistent (recommended): set the env var in your shell profile so you don’t re-type it.

Persistent examples:

Windows PowerShell profile (run once, then reopen terminal):

```powershell
notepad $PROFILE
# add a line like:
$env:DEEPSEEK_API_KEY = "..."
```

bash/zsh profile (run once, then reopen terminal):

```bash
echo 'export DEEPSEEK_API_KEY="..."' >> ~/.bashrc
```

Flags:

- `--root PATH` (optional)
  - Project root to scan (defaults to auto-detected root)
- `--env-file PATH` (default: `.env`)
  - Env file to compare against
- `--provider TEXT` (default: `anthropic`)
  - One of: `anthropic`, `openai`, or `deepseek`
- `--model TEXT`
  - Model name string passed through to the provider SDK
  - Default: `claude-3-5-sonnet-20241022`
- `--max-loops INT` (default: `30`)
  - Max tool-use loops before aborting

Environment variables:

- If `--provider anthropic`: `ANTHROPIC_API_KEY` must be set
- If `--provider openai`: `OPENAI_API_KEY` must be set
- If `--provider deepseek`: `DEEPSEEK_API_KEY` must be set

Optional environment variables:

- `DEEPSEEK_BASE_URL` (optional)
  - Override the DeepSeek OpenAI-compatible base URL
  - Default: `https://api.deepseek.com/v1`

Examples (Linux/macOS/WSL):

```bash
# Anthropic (default)
export ANTHROPIC_API_KEY="..."
envy agentic-scan --env-file .env --provider anthropic --model claude-3-5-sonnet-20241022

# OpenAI
export OPENAI_API_KEY="..."
envy agentic-scan --env-file .env --provider openai --model gpt-4o-mini

# DeepSeek (OpenAI-compatible)
export DEEPSEEK_API_KEY="..."
envy agentic-scan --env-file .env.example --provider deepseek --model deepseek-chat

# Scan a specific project root
envy agentic-scan --root /path/to/project --env-file .env

# Allow more exploration loops
envy agentic-scan --max-loops 60
```

Examples (Windows PowerShell):

```powershell
# Anthropic
$env:ANTHROPIC_API_KEY = "..."
envy agentic-scan --env-file .env --provider anthropic --model claude-3-5-sonnet-20241022

# OpenAI
$env:OPENAI_API_KEY = "..."
envy agentic-scan --env-file .env --provider openai --model gpt-4o-mini

# DeepSeek (OpenAI-compatible)
$env:DEEPSEEK_API_KEY = "..."
envy agentic-scan --env-file .env --provider deepseek --model deepseek-chat
```

---

### `envy sync push`

Encrypt and write a sync file containing only non-sensitive variables (based on an optional schema).

Flags:

- `--env-file PATH` (default: `.env`)
  - Local env file to read
- `--output-file PATH` (default: `.envy.sync`)
  - Where to write the encrypted sync file
- `--key TEXT` (optional)
  - A Fernet key used to encrypt/decrypt
  - If omitted, Envy will look for `ENVY_SYNC_KEY`
- `--schema-file PATH` (optional)
  - If provided, used to determine which variables are considered sensitive and should be excluded

Examples:

```bash
# Push using an explicit key
envy sync push --env-file .env --output-file .envy.sync --key "$ENVY_SYNC_KEY"

# Push using ENVY_SYNC_KEY from the environment
export ENVY_SYNC_KEY="..."
envy sync push --env-file .env --output-file .envy.sync

# Use a schema to prevent syncing sensitive keys
envy sync push --env-file .env --schema-file envy.schema.json --output-file .envy.sync
```

---

### `envy sync pull`

Decrypt a sync file and merge it into a local `.env`.

Flags:

- `--input-file PATH` (default: `.envy.sync`)
  - The encrypted sync file
- `--env-file PATH` (default: `.env`)
  - Local env file to update
- `--key TEXT` (optional)
  - Fernet key (or use `ENVY_SYNC_KEY`)
- `--overwrite` (default: false)
  - If set, overwrite existing values in the local env file

Examples:

```bash
# Pull into .env (do not overwrite existing values)
envy sync pull --input-file .envy.sync --env-file .env --key "$ENVY_SYNC_KEY"

# Pull and overwrite existing values
envy sync pull --input-file .envy.sync --env-file .env --key "$ENVY_SYNC_KEY" --overwrite

# Use ENVY_SYNC_KEY from environment
export ENVY_SYNC_KEY="..."
envy sync pull --input-file .envy.sync --env-file .env
```

---

## Notes / troubleshooting

### Generating an `ENVY_SYNC_KEY`

`envy sync push` / `envy sync pull` use a Fernet key (a URL-safe base64 string). You can provide it as `--key` or via `ENVY_SYNC_KEY`.

Generate one with Python:

Linux/macOS/WSL:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Windows PowerShell:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Then set it:

```bash
export ENVY_SYNC_KEY="<paste-key-here>"
```

```powershell
$env:ENVY_SYNC_KEY = "<paste-key-here>"
```

### “Command not found: envy”

- Ensure you installed the package into the environment you are using
- Try `python -m envy.main --help` to verify the module is importable
- If you used a virtual environment, ensure it is activated

### Agentic scan dependencies

This project declares `anthropic` and `openai` as dependencies. If you installed a minimal variant or vendor packages differently, install them explicitly:

```bash
pip install anthropic openai
```

### Security reminder

- Never commit real secrets to git
- Prefer storing API keys in your shell environment or a secret manager
- Never hardcode API keys into the codebase or publish them to PyPI
- Treat `.envy.sync` as sensitive if it contains any values you wouldn’t want public
