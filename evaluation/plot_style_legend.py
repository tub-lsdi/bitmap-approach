from __future__ import annotations

import argparse

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

try:
    from plot_style import (
        _AI_TO_HATCH,
        _ALGO_TO_HATCH,
        _CORPUS_TO_CMAP,
        apply_theme,
        get_corpus_palette,
    )
except ModuleNotFoundError:
    from evaluation.plot_style import (
        _AI_TO_HATCH,
        _ALGO_TO_HATCH,
        _CORPUS_TO_CMAP,
        apply_theme,
        get_corpus_palette,
    )


def collect_base_colors() -> list[tuple[str, tuple[float, float, float, float]]]:
    """Return representative colors for each corpus."""
    entries: list[tuple[str, tuple[float, float, float, float]]] = []
    label_map = {"wdc": "Dresden Web Table Corpus", "wiki": "WikiTables", "git": "GitTables"}
    for corpus in sorted(_CORPUS_TO_CMAP):
        label = label_map.get(corpus, corpus.upper())
        entries.append((label, get_corpus_palette(corpus, 1)[0]))
    return entries


def collect_hatch_styles() -> list[tuple[str, str]]:
    """Return all defined hatch patterns from algorithms and AI variants."""
    entries: list[tuple[str, str]] = []
    algo_labels = {"cs_jp": "CS JP LP", "rs_jp": "RS JP"}
    ai_labels = {"ai_naiv": "AI Naive", "ai_context": "AI Context"}
    for label, hatch in _ALGO_TO_HATCH.items():
        entries.append((f"ALGORITHM: {algo_labels.get(label, label)}", hatch))
    for label, hatch in _AI_TO_HATCH.items():
        entries.append((f"AI VARIANT: {ai_labels.get(label, label)}", hatch))
    return entries


def draw_color_column(
    ax: plt.Axes, entries: list[tuple[str, tuple[float, float, float, float]]]
) -> None:
    """Visualize the palette column."""
    swatch_width = 1.6
    swatch_height = 0.8

    for idx, (label, color) in enumerate(entries):
        y = len(entries) - idx - 1
        rect = Rectangle(
            (0, y), swatch_width, swatch_height, facecolor=color, edgecolor="black"
        )
        ax.add_patch(rect)
        ax.text(
            swatch_width + 0.2,
            y + swatch_height / 2,
            label,
            va="center",
            ha="left",
            fontsize=11,
        )

    ax.set_xlim(0, swatch_width + 3.5)
    ax.set_ylim(-0.2, len(entries) + 0.2)
    ax.set_title("Corpus colors", fontsize=13, weight="bold")
    ax.axis("off")


def draw_hatch_column(ax: plt.Axes, entries: list[tuple[str, str]]) -> None:
    """Visualize the hatch-pattern column."""
    swatch_width = 1.6
    swatch_height = 0.8
    fill_color = "#f2f2f2"

    for idx, (label, hatch) in enumerate(entries):
        y = len(entries) - idx - 1
        rect = Rectangle(
            (0, y),
            swatch_width,
            swatch_height,
            facecolor=fill_color,
            edgecolor="black",
            hatch=hatch or None,
            linewidth=1.2,
        )
        ax.add_patch(rect)

        ax.text(
            swatch_width + 0.2,
            y + swatch_height / 2,
            label,
            va="center",
            ha="left",
            fontsize=11,
        )

    ax.set_xlim(0, swatch_width + 3.5)
    ax.set_ylim(-0.2, len(entries) + 0.2)
    ax.set_title("Hatch patterns", fontsize=13, weight="bold")
    ax.axis("off")


def build_plot() -> plt.Figure:
    """Create the legend overview figure."""
    apply_theme()
    fig, axes = plt.subplots(
        1,
        2,
        figsize=(10, 5),
        gridspec_kw={"width_ratios": [1, 1], "wspace": 0.8},
    )

    color_entries = collect_base_colors()
    hatch_entries = collect_hatch_styles()

    draw_color_column(axes[0], color_entries)
    draw_hatch_column(axes[1], hatch_entries)

    fig.suptitle("Plot style overview", fontsize=16, weight="bold")
    return fig


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualize plot style colors and hatch patterns."
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Optional path to save the figure (PNG). If omitted, the plot is shown interactively.",
    )
    args = parser.parse_args()

    fig = build_plot()

    if args.output:
        fig.savefig(args.output, dpi=300, bbox_inches="tight", transparent=True)
        print(f"Legend figure saved to {args.output}")
        plt.close(fig)
    else:
        plt.show()


if __name__ == "__main__":
    main()
