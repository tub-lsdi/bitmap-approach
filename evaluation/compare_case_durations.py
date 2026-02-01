import argparse
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Sequence, Tuple

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import polars as pl
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.plot_style import (
    apply_theme,
    build_styles,
    format_label,
    parse_style_tokens,
    save_figure,
)
from evaluation.utils import load_results


def process_directory(dir_path: str) -> pl.DataFrame:
    """Aggregate benchmark_* JSON files in a directory and return mean case durations."""
    if not os.path.isdir(dir_path):
        return pl.DataFrame()

    benchmark_files = sorted(
        os.path.join(dir_path, f)
        for f in os.listdir(dir_path)
        if f.startswith("benchmark_") and os.path.isfile(os.path.join(dir_path, f))
    )
    if not benchmark_files:
        return pl.DataFrame()

    case_durations: Dict[int, List[float]] = defaultdict(list)
    for file_path in benchmark_files:
        cases = load_results(file_path)
        for case in cases:
            case_number = case.get("case_number")
            if case_number is None:
                continue
            duration = case.get("duration_seconds")
            try:
                duration_value = float(duration) if duration is not None else 0.0
            except (TypeError, ValueError):
                duration_value = 0.0
            case_durations[int(case_number)].append(duration_value)

    records: List[Dict[str, Any]] = []
    normalized = os.path.normpath(dir_path)
    parent = os.path.basename(os.path.dirname(normalized))
    leaf = os.path.basename(normalized)
    label = f"{parent}/{leaf}"
    for case_num, durations in case_durations.items():
        if durations:
            mean_duration = float(sum(durations) / len(durations))
            records.append({"case": case_num, "duration": mean_duration, "file": label})

    return pl.DataFrame(records) if records else pl.DataFrame()


def summarize_dataframe(df: pl.DataFrame) -> Dict[str, float]:
    """Compute summary statistics for a single file."""
    summary = df.select(
        [
            pl.col("duration").mean().alias("mean_duration"),
            pl.col("duration").median().alias("median_duration"),
            pl.col("duration").max().alias("max_duration"),
            pl.col("duration").sum().alias("total_duration"),
            pl.count().alias("num_cases"),
        ]
    )
    row = summary.to_dicts()[0]
    return {
        "mean_duration": float(row["mean_duration"]),
        "median_duration": float(row["median_duration"]),
        "max_duration": float(row["max_duration"]),
        "total_duration": float(row["total_duration"]),
        "num_cases": int(row["num_cases"]),
    }


def format_file_label(label: str) -> str:
    """Format a file label, converting algorithm codes to human-readable names."""
    style = parse_style_tokens(label)
    formatted = format_label(style)

    # Try to preserve the corpus/dataset prefix if it exists
    # Common prefixes: DWTC, Git Tables, Wiki Tables, etc.
    prefixes = ["DWTC", "Git Tables", "Wiki Tables"]
    for prefix in prefixes:
        if label.startswith(prefix):
            return f"{prefix} {formatted}"

    # If no recognized prefix, just return the formatted part
    return formatted


def build_style_map(file_order: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    return build_styles(file_order)


def plot_single_file(
    df: pl.DataFrame,
    styles: Dict[str, Dict[str, Any]],
    title: str,
    output: str | None,
):
    pdf = df.sort("case").to_pandas()
    file_name = pdf["file"].iloc[0]
    style = styles[file_name]

    num_cases = len(pdf["case"])
    fig_width = max(10, min(24, num_cases * 0.35))
    fig_height = 6
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    pdf_cases = [float(c) for c in pdf["case"].tolist() if c is not None]
    pdf_durations = [
        float(d) if d is not None else 0.0 for d in pdf["duration"].tolist()
    ]
    ax.bar(
        pdf_cases,
        pdf_durations,
        color=style["facecolor"],
        edgecolor=style["edgecolor"],
        linewidth=0.6,
        hatch=style["hatch"],
        alpha=style["alpha"],
    )

    ax.set_title(title or f"Case Duration per Benchmark – {file_name}")
    ax.set_xlabel("Case")
    ax.set_ylabel("Duration (s)")
    ax.set_xticks(pdf_cases)  # type: ignore[arg-type]
    ax.set_xticklabels([str(c) for c in pdf_cases], rotation=45, ha="right")
    ax.set_ylim(bottom=0)
    max_duration = float(pdf["duration"].max()) if not pdf.empty else 0.0
    tick_interval = 5 if max_duration < 60 else 60
    ax.yaxis.set_major_locator(ticker.MultipleLocator(tick_interval))
    ax.grid(axis="y", linestyle="--", alpha=0.45)

    legend_handle = Patch(
        facecolor=style["facecolor"],
        edgecolor=style["edgecolor"],
        hatch=style["hatch"],
        label=format_file_label(file_name),
    )
    ax.legend(
        handles=[legend_handle],
        title="Legend",
        bbox_to_anchor=(1.01, 1),
        loc="upper left",
    )

    plt.tight_layout()
    if output:
        save_figure(output)
    else:
        plt.show()
    plt.close(fig)


def annotate_missing_cases(
    ax: Axes,
    missing: Dict[int, List[str]],
    styles: Dict[str, Dict[str, Any]],
    file_order: Sequence[str],
    legend_handles: List[Any],
    legend_labels: List[str],
):
    if not missing:
        return

    missing_files = set()
    for files in missing.values():
        missing_files.update(files)

    for case, files in missing.items():
        width = 0.08
        base_offset = -(len(files) - 1) * width / 2
        for idx, file_name in enumerate(files):
            offset = base_offset + idx * width
            ax.scatter(
                float(case + offset),
                0.0,
                marker="x",
                color=styles[file_name]["facecolor"],
                s=60,
                zorder=6,
                linewidths=1.5,
            )

    for file_name in file_order:
        if file_name in missing_files:
            handle = Line2D(
                [],
                [],
                color=styles[file_name]["facecolor"],
                marker="x",
                linestyle="None",
                markersize=8,
                label=f"{format_file_label(file_name)} (missing case)",
            )
            legend_handles.append(handle)
            legend_labels.append(str(handle.get_label()))


def plot_layered_files(
    dfs: List[pl.DataFrame],
    styles: Dict[str, Dict[str, Any]],
    title: str,
    output: str | None,
):
    combined = pl.concat(dfs)
    if combined.is_empty():
        return

    cases = sorted(int(c) for c in combined["case"].to_list() if c is not None)
    file_order: List[str] = []
    for df in dfs:
        if df.is_empty():
            continue
        name = df["file"][0]
        if name not in file_order:
            file_order.append(name)

    data_lookup: Dict[Tuple[int, str], float] = {}
    for row in combined.iter_rows(named=True):
        data_lookup[(int(row["case"]), str(row["file"]))] = float(
            row["duration"] if row["duration"] is not None else 0.0
        )

    missing: Dict[int, List[str]] = defaultdict(list)
    max_duration = float(combined["duration"].max()) if combined.height > 0 else 0.0

    num_cases = len(cases)
    fig_width = max(12, min(30, num_cases * 0.35))
    fig_height = max(6, len(file_order) * 0.8 + 4)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

    for case in cases:
        entries: List[Tuple[float, str]] = []
        for file_name in file_order:
            duration = data_lookup.get((case, file_name))
            if duration is None:
                missing[case].append(str(file_name))
                continue
            entries.append((duration, file_name))

        entries.sort(key=lambda item: item[0])

        for order_idx, (duration, file_name) in enumerate(entries):
            layer_zorder = 2 + (len(entries) - order_idx)
            style = styles[file_name]
            ax.bar(
                case,
                duration,
                width=0.65,
                color=style["facecolor"],
                alpha=style["alpha"],
                edgecolor=style["edgecolor"],
                hatch=style["hatch"],
                linewidth=0.6,
                zorder=layer_zorder,
            )

    ax.set_title(title or "Case Duration per Benchmark")
    ax.set_xlabel("Case")
    ax.set_ylabel("Duration (s)")
    case_ticks = [c for c in cases]
    ax.set_xticks(case_ticks)  # type: ignore[arg-type]
    ax.set_xticklabels([str(c) for c in case_ticks], rotation=45, ha="right")
    ax.set_ylim(bottom=0)
    tick_interval = 5 if max_duration < 60 else 60
    ax.yaxis.set_major_locator(ticker.MultipleLocator(tick_interval))
    ax.grid(axis="y", linestyle="--", alpha=0.45)

    legend_handles = [
        Patch(
            facecolor=styles[file_name]["facecolor"],
            edgecolor=styles[file_name]["edgecolor"],
            hatch=styles[file_name]["hatch"],
            label=format_file_label(file_name),
        )
        for file_name in file_order
    ]
    legend_labels = [str(handle.get_label()) for handle in legend_handles]

    annotate_missing_cases(
        ax, missing, styles, file_order, legend_handles, legend_labels
    )

    ax.legend(
        legend_handles,
        legend_labels,
        title="Legend",
        bbox_to_anchor=(1.01, 1),
        loc="upper left",
    )

    plt.tight_layout()
    if output:
        save_figure(output)
    else:
        plt.show()
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize per-case benchmark durations."
    )
    parser.add_argument(
        "--directories",
        nargs="+",
        required=True,
        help="One or more directories containing benchmark_* JSON files.",
    )
    parser.add_argument(
        "--output", help="Optional path to save the plot (e.g., durations.png)."
    )
    parser.add_argument("--title", help="Optional title override for the plot.")
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="DIR=LABEL",
        help="Override the plotted label for a directory (repeatable, e.g., /runs/expA=Experiment A).",
    )
    parser.add_argument(
        "--summary", action="store_true", help="Print summary statistics per file."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    label_overrides: Dict[str, str] = {}
    for entry in args.label:
        if "=" not in entry:
            print(f"Warning: invalid label override, expected DIR=LABEL -> {entry}")
            continue
        raw_dir, custom_label = entry.split("=", 1)
        normalized_dir = os.path.normpath(os.path.abspath(raw_dir))
        label_overrides[normalized_dir] = custom_label
    apply_theme()

    dataframes: List[pl.DataFrame] = []
    for dir_path in args.directories:
        if not os.path.isdir(dir_path):
            print(f"Warning: directory not found -> {dir_path}")
            continue
        df = process_directory(dir_path)
        if df.is_empty():
            print(f"Warning: no duration data in -> {dir_path}")
            continue
        normalized_dir = os.path.normpath(os.path.abspath(dir_path))
        override_label = label_overrides.get(normalized_dir)
        if override_label:
            df = df.with_columns(pl.lit(override_label).alias("file"))
        dataframes.append(df)

    if not dataframes:
        print("No valid benchmark files to process.")
        return

    if args.summary:
        for df in dataframes:
            file_name = df["file"][0]
            stats = summarize_dataframe(df)
            print(f"Summary for {file_name}:")
            print(f"  Cases      : {stats['num_cases']}")
            print(f"  Mean (s)   : {stats['mean_duration']:.2f}")
            print(f"  Median (s) : {stats['median_duration']:.2f}")
            print(f"  Max (s)    : {stats['max_duration']:.2f}")
            print(f"  Total (s)  : {stats['total_duration']:.2f}")
            print("-" * 40)

    file_order = [df["file"][0] for df in dataframes]
    styles = build_style_map(file_order)

    if len(dataframes) == 1:
        plot_single_file(dataframes[0], styles, args.title, args.output)
    else:
        plot_layered_files(dataframes, styles, args.title, args.output)


if __name__ == "__main__":
    main()
