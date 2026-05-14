"""Compatibility entrypoint.

The real CLI lives in `envy.main` and is exposed via the `envy` console script.
This file allows `python cli.py ...` to behave the same way.
"""

from envy.main import cli


if __name__ == "__main__":
    cli()