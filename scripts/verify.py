"""Run the repository quality gate in the activated environment."""

import subprocess


def main() -> None:
    for command in (
        ["ruff", "check", "."],
        ["ruff", "format", "--check", "."],
        ["pyright"],
        ["pytest"],
    ):
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
