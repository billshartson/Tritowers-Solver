"""Stage the private Space runtime only. Does not create, push or deploy a Space."""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "app.py", "web_app.py", "solver_ui.py", "solver.py", "tritowers_cli.py",
    "requirements.txt", "MODEL_CARD.md",
)


def stage(destination, source=ROOT):
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if destination == source or source in destination.parents:
        raise ValueError("Destination must be outside the source checkout.")
    required = [source / name for name in (*FILES, "README-SPACE.md")]
    vision = source / "tritowers_vision"
    if any(not path.is_file() for path in required) or not vision.is_dir() or not (source / "web" / "index.html").is_file():
        raise ValueError("Incomplete source checkout: runtime files are missing.")
    if destination.exists():
        raise ValueError("Destination already exists; use a new empty path.")
    destination.mkdir(parents=True)
    for name in FILES:
        shutil.copy2(source / name, destination / name)
    shutil.copy2(source / "README-SPACE.md", destination / "README.md")
    shutil.copytree(source / "web", destination / "web")
    shutil.copytree(vision, destination / "tritowers_vision",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        result = stage(args.destination)
    except ValueError as error:
        parser.error(str(error))
    print(f"Staged runtime at {result}. No Space created or uploaded.")
