"""Allow ``python -m pyheic_struct`` to behave like the CLI."""

from .cli import main

if __name__ == "__main__":  # pragma: no cover
    main()
