# Envy

Envy is a CLI for validating environment variables, generating docs, scanning for likely secret leaks, and syncing non-sensitive config with encryption.

## Setup

Use the WSL virtual environment in this repo:

```bash
source .venv-wsl/bin/activate
python -m envy.main --help
```

## Commands

Validate a `.env` file against `envy.schema.json` or `.env.template`:

```bash
python -m envy.main check --env-file .env
```

Generate `README_ENV.md` from the schema:

```bash
python -m envy.main docs --schema-file envy.schema.json --output README_ENV.md
```

Scan for high-entropy strings before commit:

```bash
python -m envy.main scan --staged
```

Install the pre-commit hook:

```bash
python -m envy.main install-hook
```

Encrypt and share non-sensitive settings:

```bash
python -m envy.main sync push --env-file .env --output-file .envy.sync --key "$ENVY_SYNC_KEY"
python -m envy.main sync pull --input-file .envy.sync --env-file .env --key "$ENVY_SYNC_KEY"
```

## Schema example

See `envy.schema.json` for a starter schema you can customize.
