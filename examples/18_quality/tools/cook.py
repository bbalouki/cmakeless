"""Cook every asset file: here, upper-case it into the output directory."""

import sys
from pathlib import Path


def main() -> None:
    """Read assets from argv[1], write cooked copies into argv[2]."""
    source, destination = Path(sys.argv[1]), Path(sys.argv[2])
    destination.mkdir(parents=True, exist_ok=True)
    for asset in sorted(source.glob("*.txt")):
        (destination / asset.name).write_text(asset.read_text().upper())


if __name__ == "__main__":
    main()
