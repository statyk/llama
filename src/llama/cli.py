import typer

app = typer.Typer(help="Live Music Archive -> radio station pipeline")


@app.callback()
def main() -> None:
    """Find, vet, research, and package LMA concerts for broadcast."""


@app.command()
def version() -> None:
    """Print the llama version."""
    import llama

    typer.echo(llama.__version__)
