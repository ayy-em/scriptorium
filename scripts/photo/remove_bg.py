"""Remove background from images, producing PNGs with alpha transparency."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from PIL import Image, ImageOps

from core.argparse import ScriptoriumParser
from core.downloads import reporting_downloads
from core.images import ensure_image_formats
from core.outputs import deduplicate, default_stem, resolve_output, resolve_output_dir
from core.paths import inputs_dir, move_to_past_inputs
from scripts.formats._utils import IMAGE_EXTS, find_files, single_source

TITLE = "Remove background"
DESCRIPTION = "Remove image backgrounds using AI, outputting transparent PNGs."
ACCEPTS: set[str] = {"image"}

_THEME = "photo"

MODELS = [
    "u2net",
    "u2netp",
    "u2net_human_seg",
    "isnet-general-use",
    "isnet-anime",
    "silueta",
    "birefnet-general",
    "birefnet-general-lite",
    "birefnet-portrait",
    "bria-rmbg",
]

DEFAULT_MODEL = "u2net"

#: Weights file per model, all published under one rembg GitHub release. Kept
#: here rather than read out of rembg because each session class buries its URL
#: inside a method; a test checks the table against the installed sources.
WEIGHTS_RELEASE_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
WEIGHTS_FILES = {
    "u2net": "u2net.onnx",
    "u2netp": "u2netp.onnx",
    "u2net_human_seg": "u2net_human_seg.onnx",
    "isnet-general-use": "isnet-general-use.onnx",
    "isnet-anime": "isnet-anime.onnx",
    "silueta": "silueta.onnx",
    "birefnet-general": "BiRefNet-general-epoch_244.onnx",
    "birefnet-general-lite": "BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx",
    "birefnet-portrait": "BiRefNet-portrait-epoch_150.onnx",
    "bria-rmbg": "bria-rmbg-2.0.onnx",
}


@dataclass(frozen=True)
class Preset:
    """One named bundle of model and edge-treatment choices.

    Attributes:
        model: The rembg session to load.
        alpha_matting: Refine soft edges with alpha matting.
        post_process_mask: Clean noise and jaggies out of the mask.
    """

    model: str
    alpha_matting: bool = False
    post_process_mask: bool = False


#: Named shorthands, in the order ``--all-presets`` runs them. None is "better"
#: than another on every image — u2net regularly beats the larger models on
#: some photos — which is why they are named for cost, not quality, and why
#: there is a flag to run all three side by side. ``fast`` is the historical
#: default, so a bare run is unchanged. Every model downloads its weights on
#: first use; ``hq`` uses the lite BiRefNet (~215MB) rather than the full one
#: (~950MB), which stays an explicit ``--model`` choice.
PRESETS: dict[str, Preset] = {
    "fast": Preset(DEFAULT_MODEL),
    "balanced": Preset("isnet-general-use", post_process_mask=True),
    "hq": Preset("birefnet-general-lite", alpha_matting=True, post_process_mask=True),
}

DEFAULT_PRESET = "fast"


def settings_for(
    preset: str,
    *,
    model: str | None = None,
    alpha_matting: bool = False,
    post_process_mask: bool = False,
) -> Preset:
    """Resolve the effective model and edge options for one run.

    Explicit flags only ever add to a preset: a boolean CLI flag cannot say
    "off", so a preset that enables matting stays enabled.

    Args:
        preset: A key of ``PRESETS``.
        model: An explicit ``--model`` value, or None to use the preset's.
        alpha_matting: Whether ``--alpha-matting`` was passed.
        post_process_mask: Whether ``--post-process-mask`` was passed.

    Returns:
        The merged settings.

    Raises:
        ValueError: If *preset* is not a known preset.
    """
    if preset not in PRESETS:
        raise ValueError(f"unknown preset: {preset!r} (expected one of {', '.join(PRESETS)})")
    base = PRESETS[preset]
    return Preset(
        model=model or base.model,
        alpha_matting=base.alpha_matting or alpha_matting,
        post_process_mask=base.post_process_mask or post_process_mask,
    )


def presets_for_run(preset: str, *, all_presets: bool) -> tuple[str, ...]:
    """Return the presets one invocation will run, in order.

    Args:
        preset: The ``--preset`` value.
        all_presets: Whether ``--all-presets`` was passed.

    Returns:
        Every preset when comparing, otherwise just the one asked for.
    """
    return tuple(PRESETS) if all_presets else (preset,)


def models_for_args(args: argparse.Namespace) -> list[str]:
    """Return every model a parsed invocation would load.

    The web UI calls this before a run to warn about weights that will be
    downloaded, so it must agree exactly with what ``run()`` does.

    Args:
        args: Namespace from ``get_parser()``.

    Returns:
        Model names in run order, without duplicates.
    """
    models: list[str] = []
    for name in presets_for_run(args.preset, all_presets=args.all_presets):
        chosen = settings_for(name, model=None if args.all_presets else args.model).model
        if chosen not in models:
            models.append(chosen)
    return models


def weights_url(model: str) -> str | None:
    """Return where a model's weights are downloaded from.

    Args:
        model: A rembg model name.

    Returns:
        The release asset URL, or None for a model not in the table.
    """
    filename = WEIGHTS_FILES.get(model)
    return None if filename is None else WEIGHTS_RELEASE_URL + filename


def _load_session(model: str) -> Any:
    """Create a rembg session, reporting the weights download if there is one.

    Args:
        model: The model to load.

    Returns:
        A rembg session.
    """
    from rembg import new_session  # noqa: PLC0415

    with reporting_downloads(f"Downloading {model} weights"):
        return new_session(model)


def hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    """Parse a hex color string into an RGBA tuple for rembg's bgcolor option.

    Accepts 3-digit shorthand ("#fff"), 6-digit ("#ffffff") and 8-digit
    with alpha ("#ffffffff") forms, with or without the leading "#".

    Args:
        value: Hex color string, e.g. "#ffffff".

    Returns:
        Tuple of (red, green, blue, alpha) integers in the 0-255 range.

    Raises:
        ValueError: If the string is not a valid hex color.
    """
    digits = value.strip().lstrip("#")
    if len(digits) == 3:  # noqa: PLR2004
        digits = "".join(c * 2 for c in digits)
    if len(digits) == 6:  # noqa: PLR2004
        digits += "ff"
    if len(digits) != 8:  # noqa: PLR2004
        raise ValueError(f"invalid hex color: {value!r} (expected #rgb, #rrggbb or #rrggbbaa)")
    try:
        channels = tuple(int(digits[i : i + 2], 16) for i in range(0, 8, 2))
    except ValueError:
        raise ValueError(f"invalid hex color: {value!r} (non-hex characters)") from None
    return channels  # type: ignore[return-value]


def remove_bg(  # noqa: PLR0913
    source: Path,
    output: Path,
    *,
    model: str = DEFAULT_MODEL,
    alpha_matting: bool = False,
    alpha_matting_foreground_threshold: int = 240,
    alpha_matting_background_threshold: int = 10,
    alpha_matting_erode_size: int = 10,
    only_mask: bool = False,
    post_process_mask: bool = False,
    bgcolor: tuple[int, int, int, int] | None = None,
    session: Any = None,
) -> None:
    """Remove the background from a single image and save as PNG.

    Args:
        source: Path to the input image.
        output: Path for the output PNG file.
        model: Name of the rembg segmentation model to use.
        alpha_matting: Refine edges with alpha matting for soft boundaries.
        alpha_matting_foreground_threshold: Confidence (0-255) above which
            pixels are treated as solid foreground during matting.
        alpha_matting_background_threshold: Confidence (0-255) below which
            pixels are treated as definite background during matting.
        alpha_matting_erode_size: Width in pixels of the uncertain edge band
            that matting blends between foreground and background.
        only_mask: Save the black-and-white segmentation mask instead of
            the cutout image.
        post_process_mask: Clean up noise and jagged edges in the mask.
        bgcolor: Optional RGBA fill for the removed background; None keeps
            the background transparent.
        session: Pre-built rembg session to reuse (batch mode); when None a
            session is created from ``model``.
    """
    from rembg import remove  # noqa: PLC0415

    if session is None:
        session = _load_session(model)

    ensure_image_formats()
    img = ImageOps.exif_transpose(Image.open(source))
    result = remove(
        img,
        session=session,
        alpha_matting=alpha_matting,
        alpha_matting_foreground_threshold=alpha_matting_foreground_threshold,
        alpha_matting_background_threshold=alpha_matting_background_threshold,
        alpha_matting_erode_size=alpha_matting_erode_size,
        only_mask=only_mask,
        post_process_mask=post_process_mask,
        bgcolor=bgcolor,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, format="PNG")


def remove_bg_batch(  # noqa: PLR0913
    source: Path,
    outputs_dir: Path,
    *,
    model: str = DEFAULT_MODEL,
    alpha_matting: bool = False,
    alpha_matting_foreground_threshold: int = 240,
    alpha_matting_background_threshold: int = 10,
    alpha_matting_erode_size: int = 10,
    only_mask: bool = False,
    post_process_mask: bool = False,
    bgcolor: tuple[int, int, int, int] | None = None,
    name_prefix: str = "",
    archive: bool = True,
) -> list[Path]:
    """Remove backgrounds from a single image or all images in a directory.

    The segmentation model is loaded once and reused for every image.
    Successfully processed files that live inside the shared inputs/
    directory are archived to inputs/processed/ afterwards, unless
    ``archive`` is False because another pass over the same files follows.

    Args:
        source: Source image file or directory of images.
        outputs_dir: Directory where output PNGs are written.
        model: Name of the rembg segmentation model to use.
        alpha_matting: Refine edges with alpha matting for soft boundaries.
        alpha_matting_foreground_threshold: Confidence (0-255) above which
            pixels are treated as solid foreground during matting.
        alpha_matting_background_threshold: Confidence (0-255) below which
            pixels are treated as definite background during matting.
        alpha_matting_erode_size: Width in pixels of the uncertain edge band
            that matting blends between foreground and background.
        only_mask: Save the black-and-white segmentation mask instead of
            the cutout image.
        post_process_mask: Clean up noise and jagged edges in the mask.
        bgcolor: Optional RGBA fill for the removed background; None keeps
            the background transparent.
        name_prefix: Prepended to every output filename, so runs of several
            presets over one batch stay distinguishable.
        archive: Move processed inputs to inputs/processed/ afterwards.

    Returns:
        List of successfully created output paths.

    Raises:
        FileNotFoundError: If the source path does not exist.
        RuntimeError: If any files fail in batch mode.
    """
    if not source.exists():
        raise FileNotFoundError(f"source not found: {source}")

    session = _load_session(model)
    removal_options = {
        "alpha_matting": alpha_matting,
        "alpha_matting_foreground_threshold": alpha_matting_foreground_threshold,
        "alpha_matting_background_threshold": alpha_matting_background_threshold,
        "alpha_matting_erode_size": alpha_matting_erode_size,
        "only_mask": only_mask,
        "post_process_mask": post_process_mask,
        "bgcolor": bgcolor,
    }

    outputs_dir.mkdir(parents=True, exist_ok=True)
    stamp = default_stem()

    if source.is_file():
        output = deduplicate(outputs_dir / f"{name_prefix}{stamp}.png")
        remove_bg(source, output, session=session, **removal_options)
        if archive:
            move_to_past_inputs(_THEME, source)
        return [output]

    files = find_files(source, IMAGE_EXTS)
    if not files:
        return []

    successes: list[Path] = []
    failures: list[str] = []

    for i, f in enumerate(files, 1):
        output = deduplicate(outputs_dir / f"{name_prefix}{stamp}_{i:03d}.png")
        try:
            remove_bg(f, output, session=session, **removal_options)
            successes.append(output)
            if archive:
                move_to_past_inputs(_THEME, f)
        except Exception as e:
            failures.append(f"{f.name}: {e}")

    if failures:
        bullet_list = "\n".join(f"  - {msg}" for msg in failures)
        raise RuntimeError(f"{len(failures)} of {len(files)} file(s) failed:\n{bullet_list}")

    return successes


_EXAMPLES = """
examples:
  uv run main.py photo.remove_bg
  uv run main.py photo.remove_bg portrait.jpg
  uv run main.py photo.remove_bg photos/ -o cleaned/
  uv run main.py photo.remove_bg portrait.jpg --preset hq
  uv run main.py photo.remove_bg photos/ --all-presets
  uv run main.py photo.remove_bg portrait.jpg --model birefnet-portrait --alpha-matting
  uv run main.py photo.remove_bg product.png --bgcolor "#ffffff"
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py photo.remove_bg",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        help="Source image file or directory of images (default: inputs/)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help="Output file or directory (default: outputs/photo/)",
    )
    parser.add_argument(
        "--preset",
        default=DEFAULT_PRESET,
        choices=list(PRESETS),
        ui_label="Preset",
        help=(
            f"Shorthand for a model and its edge treatment: fast ({DEFAULT_MODEL}, the default), "
            "balanced (isnet-general-use with mask clean-up), or hq (birefnet-general-lite with "
            "alpha matting and mask clean-up, slowest). No preset wins on every image — when in "
            "doubt, --all-presets. Explicit --model, --alpha-matting and --post-process-mask "
            "add to whatever the preset sets."
        ),
    )
    parser.add_argument(
        "--all-presets",
        action="store_true",
        ui_label="Run all presets",
        help=(
            "Run fast, balanced and hq one after another on the same inputs, into the same "
            "output location, with the preset name prepended to each filename — for picking "
            "the best result by eye. Ignores --preset and --model."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        choices=MODELS,
        ui_label="AI model",
        ui_advanced=True,
        help=(
            "Pick the segmentation model directly, overriding the preset's. "
            "u2net_human_seg and birefnet-portrait specialize in people; isnet-anime for "
            "illustrations; silueta is light; birefnet-general and bria-rmbg give the "
            "highest quality but are slow. Every model downloads its weights to ~/.u2net/ "
            "the first time it is used — around 170MB for most, ~950MB for "
            "birefnet-general."
        ),
    )
    parser.add_argument(
        "--alpha-matting",
        action="store_true",
        ui_label="Alpha matting",
        help=(
            "Refine edges with alpha matting — better results for soft boundaries like hair, "
            "fur or foliage, at the cost of slower processing."
        ),
        ui_advanced=True,
    )
    parser.add_argument(
        "--alpha-matting-foreground-threshold",
        type=int,
        default=240,
        metavar="0-255",
        ui_label="Foreground threshold",
        help=(
            "Only used with alpha matting. Confidence (0-255) above which a pixel is kept as "
            "solid foreground; lower values keep more of the edge region."
        ),
        ui_advanced=True,
    )
    parser.add_argument(
        "--alpha-matting-background-threshold",
        type=int,
        default=10,
        metavar="0-255",
        ui_label="Background threshold",
        help=(
            "Only used with alpha matting. Confidence (0-255) below which a pixel is fully "
            "removed as background; higher values remove more of the edge region."
        ),
        ui_advanced=True,
    )
    parser.add_argument(
        "--alpha-matting-erode-size",
        type=int,
        default=10,
        metavar="PIXELS",
        ui_label="Erode size",
        help=(
            "Only used with alpha matting. Width in pixels of the uncertain band around edges "
            "that gets smoothly blended; larger values give softer transitions."
        ),
        ui_advanced=True,
    )
    parser.add_argument(
        "--only-mask",
        action="store_true",
        ui_label="Mask only",
        help=(
            "Output the black-and-white segmentation mask (white = kept subject, "
            "black = removed background) instead of the cutout image."
        ),
        ui_advanced=True,
    )
    parser.add_argument(
        "--post-process-mask",
        action="store_true",
        ui_label="Post-process mask",
        help="Clean up the segmentation mask, reducing noise and jagged or fuzzy edges.",
        ui_advanced=True,
    )
    parser.add_argument(
        "--bgcolor",
        type=hex_to_rgba,
        default=None,
        metavar="HEX",
        ui_label="Background color",
        help=(
            "Fill the removed background with a solid color instead of transparency, "
            "e.g. #ffffff for white. Accepts #rgb, #rrggbb or #rrggbbaa."
        ),
        ui_advanced=True,
    )
    return parser


def _prefixed(path: Path, prefix: str) -> Path:
    """Prepend a preset name to an already-resolved output path.

    Args:
        path: The path ``resolve_output`` produced.
        prefix: Text to put in front of the filename; empty leaves it alone.

    Returns:
        A collision-free path with the prefix applied.
    """
    if not prefix:
        return path
    return deduplicate(path.with_name(f"{prefix}{path.name}"))


def _run_preset(args: argparse.Namespace, source: Path, preset: str, *, last: bool) -> list[Path]:
    """Process the source once with one preset's settings.

    Args:
        args: Parsed CLI arguments.
        source: Image file or directory, already collapsed by ``single_source``.
        preset: The preset to apply.
        last: Whether this is the final pass, and so the one that archives
            the inputs. Archiving earlier would hide them from the next pass.

    Returns:
        Output paths written.
    """
    settings = settings_for(
        preset,
        model=None if args.all_presets else args.model,
        alpha_matting=args.alpha_matting,
        post_process_mask=args.post_process_mask,
    )
    removal_options = {
        "model": settings.model,
        "alpha_matting": settings.alpha_matting,
        "alpha_matting_foreground_threshold": args.alpha_matting_foreground_threshold,
        "alpha_matting_background_threshold": args.alpha_matting_background_threshold,
        "alpha_matting_erode_size": args.alpha_matting_erode_size,
        "only_mask": args.only_mask,
        "post_process_mask": settings.post_process_mask,
        "bgcolor": args.bgcolor,
    }
    prefix = f"{preset}_" if args.all_presets else ""

    if source.is_file():
        out = _prefixed(resolve_output(args.output, theme=_THEME, ext=".png"), prefix)
        remove_bg(source, out, **removal_options)
        if last:
            move_to_past_inputs(_THEME, source)
        return [out]

    out_dir = resolve_output_dir(args.output, theme=_THEME)
    return remove_bg_batch(source, out_dir, name_prefix=prefix, archive=last, **removal_options)


def run() -> None:
    """CLI entrypoint. Parse arguments and run each requested preset in turn."""
    args = get_parser().parse_args()

    source = args.source if args.source is not None else inputs_dir(_THEME)

    # The web UI uploads even a single file into a per-batch directory, so a
    # directory holding exactly one image is a one-file job. Collapsing it here
    # means an explicit --output filename reaches resolve_output() instead of
    # being thrown away by the batch path.
    lone = single_source(source, IMAGE_EXTS)
    if lone is not None:
        source = lone

    presets = presets_for_run(args.preset, all_presets=args.all_presets)
    failures: list[str] = []
    for index, preset in enumerate(presets):
        if args.all_presets:
            print(f"[{preset}] {PRESETS[preset].model}", file=sys.stderr)
        try:
            for out in _run_preset(args, source, preset, last=index == len(presets) - 1):
                print(out)
        except Exception as e:
            # One preset failing must not cost the others: the point of
            # --all-presets is having every result to compare.
            failures.append(f"{preset}: {e}")
            print(f"error: {e}", file=sys.stderr)

    if failures:
        sys.exit(1)
