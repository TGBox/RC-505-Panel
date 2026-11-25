"""RC-505-Panel: Offline- und Live-Steuerung der BOSS RC-505mkII."""


def main() -> None:
    from .cli import main as cli_main
    cli_main()
