from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import matplotlib.cm as cm
import matplotlib.colors as mcolors
import numpy as np
import seaborn as sns

__all__ = [
    "ParsedStyle",
    "parse_style_tokens",
    "get_corpus_palette",
    "get_hatch",
    "build_styles",
    "apply_theme",
    "save_figure",
]


@dataclass(frozen=True)
class ParsedStyle:
    corpus: str | None
    algorithm: str | None
    ai_variant: str | None


_CORPUS_TO_CMAP = {
    "wdc": "Blues",
    "wiki": "Greens",
    "git": "Oranges",
}

_ALGO_TO_HATCH = {
    "cs_jp": "",
    "rs_jp": "//",
}

_AI_TO_HATCH = {
    "ai_naiv": ".",
    "ai_context": "x",
}


def _lower_sources(source: str) -> List[str]:
    """
    Produce a list of lowercase strings to inspect.
    Order: filename, then parent directory (if available).
    """
    source = source or ""
    parts: List[str] = []
    basename = os.path.basename(source).lower()
    if basename:
        parts.append(basename)
    parent = os.path.basename(os.path.dirname(source)).lower()
    if parent and parent not in parts:
        parts.append(parent)
    parent_parent = os.path.basename(os.path.dirname(os.path.dirname(source))).lower()
    if parent_parent and parent_parent not in parts:
        parts.append(parent_parent)
    return parts or [""]


def parse_style_tokens(source: str) -> ParsedStyle:
    """
    Parse corpus / algorithm / ai_variant tokens from a path or filename.

    Detection (case-insensitive substring):
    - corpus: wdc | wiki | git
    - algorithm: cs_jp | rs_jp
    - ai_variant (only when rs_jp is present):
        * context -> ai_context
        * naiv or naive -> ai_naiv
    """
    corpus = None
    algorithm = None
    ai_variant = None

    for token in _lower_sources(source):
        if corpus is None:
            if "wdc" in token:
                corpus = "wdc"
            elif "wiki" in token:
                corpus = "wiki"
            elif "git" in token:
                corpus = "git"

        if algorithm is None:
            if "cs_jp" in token:
                algorithm = "cs_jp"
            elif "rs_jp" in token:
                algorithm = "rs_jp"

        if algorithm == "rs_jp" and ai_variant is None:
            if "context" in token:
                ai_variant = "ai_context"
            elif "naiv" in token or "naive" in token:
                ai_variant = "ai_naiv"

    return ParsedStyle(corpus=corpus, algorithm=algorithm, ai_variant=ai_variant)


def get_corpus_palette(
    corpus: str | None, n: int
) -> List[tuple[float, float, float, float]]:
    """
    Return n RGBA colors for the requested corpus.
    Falls back to a neutral gray palette if corpus is unknown/None.
    """
    cmap_name = _CORPUS_TO_CMAP.get(corpus or "", "Greys")
    cmap = cm.get_cmap(cmap_name)
    # Avoid extremes of the colormap to keep contrast for edges/hatches
    stops = np.linspace(0.35, 0.85, max(1, n))
    return [mcolors.to_rgba(cmap(s)) for s in stops]


def _darker(
    color: tuple[float, float, float, float], factor: float = 0.8
) -> tuple[float, float, float, float]:
    r, g, b, a = color
    return (max(0.0, r * factor), max(0.0, g * factor), max(0.0, b * factor), a)


def get_hatch(style: ParsedStyle) -> str:
    """
    Resolve hatch based on AI variant (highest priority) or algorithm.
    """
    if style.ai_variant:
        return _AI_TO_HATCH.get(style.ai_variant, _AI_TO_HATCH.get("ai_naiv", "."))
    if style.algorithm:
        return _ALGO_TO_HATCH.get(style.algorithm, "")
    return ""


def build_styles(
    labels: Sequence[str],
    steps_per_label: int = 1,
    alpha: float = 0.9,
) -> Dict[str, Dict[str, Any]]:
    """
    Build deterministic styles keyed by label.

    If steps_per_label > 1, each label value will also include a "steps" list
    of style dicts (ordered light -> dark) to use across multiple series/steps.
    """
    parsed: Dict[str, ParsedStyle] = {lbl: parse_style_tokens(lbl) for lbl in labels}

    # Group labels by corpus to allocate palette slots deterministically
    corpus_groups: Dict[str | None, List[str]] = {}
    for lbl in labels:
        corpus_groups.setdefault(parsed[lbl].corpus, []).append(lbl)

    styles: Dict[str, Dict[str, Any]] = {}

    for corpus, lbls in corpus_groups.items():
        total_needed = len(lbls) * steps_per_label
        palette = get_corpus_palette(corpus, total_needed)

        for idx, lbl in enumerate(lbls):
            shade_start = idx * steps_per_label
            shade_end = shade_start + steps_per_label
            shades = palette[shade_start:shade_end]

            hatch = get_hatch(parsed[lbl])
            step_styles = []
            for color in shades:
                step_styles.append(
                    {
                        "facecolor": color,
                        "edgecolor": _darker(color),
                        "hatch": hatch,
                        "alpha": alpha,
                    }
                )

            # Default/top-level style uses the first shade
            primary = step_styles[0]
            entry: Dict[str, Any] = {
                "facecolor": primary["facecolor"],
                "edgecolor": primary["edgecolor"],
                "hatch": primary["hatch"],
                "alpha": primary["alpha"],
            }
            if steps_per_label > 1:
                entry["steps"] = step_styles
            styles[lbl] = entry

    return styles


def apply_theme():
    """
    Set a consistent seaborn theme for plots that consume this utility.
    """
    sns.set_theme(style="whitegrid", font_scale=1.0)


def save_figure(
    output_path: str,
    dpi: int = 300,
    bbox_inches: str = "tight",
) -> None:
    """
    Save the current figure in both PNG and SVG formats with transparent backgrounds.

    Args:
        output_path: Base output path (e.g., "plot.png"). The SVG will be saved
                     with the same name but .svg extension.
        dpi: Resolution for the PNG output (default: 300).
        bbox_inches: Bounding box setting (default: "tight").
    """
    import matplotlib.pyplot as plt

    # Determine base path without extension
    base, ext = os.path.splitext(output_path)
    if not ext:
        ext = ".png"

    png_path = base + ".png"
    svg_path = base + ".svg"

    # Save PNG with transparent background
    plt.savefig(
        png_path,
        dpi=dpi,
        bbox_inches=bbox_inches,
        transparent=True,
    )
    print(f"Plot saved to {png_path}")

    # Save SVG with transparent background
    plt.savefig(
        svg_path,
        format="svg",
        bbox_inches=bbox_inches,
        transparent=True,
    )
    print(f"Plot saved to {svg_path}")
