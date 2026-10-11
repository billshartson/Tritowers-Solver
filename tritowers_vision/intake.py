"""Choose a supported photo layout before reading its ranks."""
from .image import normalize_image
from . import reader
from .full_deal import read_full_deal


def read_photo(source, templates=(), manual_corners=None):
    """Return a tableau or complete-deal draft, without private grid templates.

    Grid geometry must pass its own checks before it can replace the tableau
    path. Normalize once so both detectors inspect the same oriented pixels.
    """
    image = normalize_image(source)
    full_deal = read_full_deal(image)
    if full_deal is not None:
        return full_deal
    return reader.read_photo(image, templates, manual_corners)
