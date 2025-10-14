from __future__ import annotations

import itertools
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

try:
    from PIL import Image
except ImportError:  # pragma: no cover - handled at runtime
    Image = None  # type: ignore


class PillowUnavailableError(RuntimeError):
    pass


RGBColor = Tuple[int, int, int]


def require_pillow() -> None:
    if Image is None:
        raise PillowUnavailableError(
            "Pillow is required for sprite validation. Please install it with 'pip install Pillow'."
        )


def validate_png(path: Path, expected_size: Tuple[int, int], max_colors: int = 16) -> None:
    require_pillow()
    with Image.open(path) as image:
        if image.size != expected_size:
            raise ValueError(f"{path} must be {expected_size[0]}x{expected_size[1]} pixels; got {image.size}.")
        colors = image.convert("RGBA").getcolors(maxcolors=max_colors + 1)
        if colors is None:
            raise ValueError(f"{path} uses more than {max_colors} colours.")


def read_jasc_palette(path: Path) -> List[RGBColor]:
    with path.open("r", encoding="utf-8") as handle:
        header = handle.readline().strip()
        if header != "JASC-PAL":
            raise ValueError(f"{path} is not a JASC-PAL palette.")
        version = handle.readline().strip()
        if version != "0100":
            raise ValueError(f"{path} has unsupported palette version {version!r}.")
        count_line = handle.readline().strip()
        try:
            count = int(count_line)
        except ValueError as exc:
            raise ValueError(f"{path} has invalid colour count {count_line!r}.") from exc
        if count != 16:
            raise ValueError(f"{path} must contain exactly 16 colours (found {count}).")
        colours: List[RGBColor] = []
        for _ in range(count):
            line = handle.readline()
            if not line:
                raise ValueError(f"{path} ended before all palette entries were read.")
            parts = line.strip().split()
            if len(parts) != 3:
                raise ValueError(f"{path} has malformed colour entry {line!r}.")
            try:
                r, g, b = map(int, parts)
            except ValueError as exc:
                raise ValueError(f"{path} has a non-integer colour component in {line!r}.") from exc
            if not all(0 <= value <= 255 for value in (r, g, b)):
                raise ValueError(f"{path} has colour values outside the 0-255 range in {line!r}.")
            colours.append((r, g, b))
    return colours


def write_jasc_palette(path: Path, colours: Sequence[RGBColor]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("JASC-PAL\n")
        handle.write("0100\n")
        handle.write(f"{len(colours)}\n")
        for r, g, b in colours:
            handle.write(f"{r} {g} {b}\n")


def validate_palette(path: Path) -> List[RGBColor]:
    colours = read_jasc_palette(path)
    if len(colours) != 16:
        raise ValueError(f"{path} must provide exactly 16 colours.")
    return colours


def auto_generate_shiny_palette(normal_palette: Sequence[RGBColor]) -> List[RGBColor]:
    if not normal_palette:
        raise ValueError("Normal palette is empty; cannot create shiny palette.")
    first_colour = normal_palette[0]
    rest = list(normal_palette[1:])
    if rest:
        rest = rest[1:] + rest[:1]
    return [first_colour, *rest]


def ensure_shiny_palette(normal_path: Path, shiny_path: Path) -> None:
    colours = validate_palette(normal_path)
    if shiny_path.exists():
        validate_palette(shiny_path)
        return
    shiny_colours = auto_generate_shiny_palette(colours)
    write_jasc_palette(shiny_path, shiny_colours)
