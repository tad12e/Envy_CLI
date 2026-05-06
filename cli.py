import click

@click.group()
def cli():
    """Envy — environment variable manager for backend projects."""
    pass

@cli.command()
def check():
    """Check that all required env variables exist."""
    click.echo("Checking your environment...")

if __name__ == "__main__":
    cli()