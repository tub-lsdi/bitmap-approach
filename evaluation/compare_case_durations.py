import argparse
import os
import sys
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import polars as pl
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.utils import get_short_filename, load_results


def process_file(file_path: str) -> pl.DataFrame:
    """Load a benchmark JSON file and return a DataFrame with case durations."""
    cases = load_results(file_path)
    filename = get_short_filename(file_path)
    records: List[Dict[str, float]] = []

    for case in cases:
        case_number = case.get("case_number")
        if case_number is None:
            continue
        duration = case.get("duration_seconds")
        try:
            duration_value = float(duration) if duration is not None else 0.0
        except (TypeError, ValueError):
            duration_value = 0.0
        records.append(
            {"case": int(case_number), "duration": duration_value, "file": filename}
        )

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


def build_color_map(file_order: Sequence[str]) -> Dict[str, Tuple[float, float, float]]:
    palette = sns.color_palette("colorblind", len(file_order))
    return {file_name: palette[idx] for idx, file_name in enumerate(file_order)}


def plot_single_file(
    df: pl.DataFrame,
    colors: Dict[str, Tuple[float, float, float]],
    title: str,
    output: str | None,
):
    pdf = df.sort("case").to_pandas()
    file_name = pdf["file"].iloc[0]
    color = colors[file_name]

    num_cases = len(pdf["case"])
    fig_width = max(10, min(24, num_cases * 0.35))
    fig_height = 6
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.bar(pdf["case"], pdf["duration"], color=color, edgecolor="white", linewidth=0.6)

    ax.set_title(title or f"Case Duration per Benchmark – {file_name}")
    ax.set_xlabel("Case")
    ax.set_ylabel("Duration (s)")
    ax.set_xticks(pdf["case"])
    ax.set_xticklabels(pdf["case"], rotation=45, ha="right")
    ax.set_ylim(bottom=0)
    max_duration = float(pdf["duration"].max()) if not pdf.empty else 0.0
    tick_interval = 5 if max_duration < 60 else 60
    ax.yaxis.set_major_locator(ticker.MultipleLocator(tick_interval))
    ax.grid(axis="y", linestyle="--", alpha=0.45)

    legend_handle = Patch(facecolor=color, edgecolor="white", label=file_name)
    ax.legend(
        handles=[legend_handle],
        title="File",
        bbox_to_anchor=(1.01, 1),
        loc="upper left",
    )

    plt.tight_layout()
    if output:
        plt.savefig(output, bbox_inches="tight")
        print(f"Plot saved to {output}")
    else:
        plt.show()
    plt.close(fig)


def annotate_missing_cases(
    ax: plt.Axes,
    missing: Dict[int, List[str]],
    colors: Dict[str, Tuple[float, float, float]],
    file_order: Sequence[str],
    legend_handles: List[Patch | Line2D],
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
                case + offset,
                0,
                marker="x",
                color=colors[file_name],
                s=60,
                zorder=6,
                linewidths=1.5,
            )

    for file_name in file_order:
        if file_name in missing_files:
            handle = Line2D(
                [],
                [],
                color=colors[file_name],
                marker="x",
                linestyle="None",
                markersize=8,
                label=f"{file_name} (missing case)",
            )
            legend_handles.append(handle)
            legend_labels.append(handle.get_label())


def plot_layered_files(
    dfs: List[pl.DataFrame],
    colors: Dict[str, Tuple[float, float, float]],
    title: str,
    output: str | None,
):
    combined = pl.concat(dfs)
    if combined.is_empty():
        return

    cases = sorted(set(combined["case"].to_list()))
    file_order: List[str] = []
    for df in dfs:
        if df.is_empty():
            continue
        name = df["file"][0]
        if name not in file_order:
            file_order.append(name)

    data_lookup: Dict[Tuple[int, str], float] = {}
    for row in combined.iter_rows(named=True):
        data_lookup[(row["case"], row["file"])] = float(row["duration"])

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
                missing[case].append(file_name)
                continue
            entries.append((duration, file_name))

        entries.sort(key=lambda item: item[0])

        for order_idx, (duration, file_name) in enumerate(entries):
            layer_zorder = 2 + (len(entries) - order_idx)
            ax.bar(
                case,
                duration,
                width=0.65,
                color=colors[file_name],
                alpha=0.9,
                edgecolor="white",
                linewidth=0.6,
                zorder=layer_zorder,
            )

    ax.set_title(title or "Case Duration per Benchmark")
    ax.set_xlabel("Case")
    ax.set_ylabel("Duration (s)")
    ax.set_xticks(cases)
    ax.set_xticklabels(cases, rotation=45, ha="right")
    ax.set_ylim(bottom=0)
    tick_interval = 5 if max_duration < 60 else 60
    ax.yaxis.set_major_locator(ticker.MultipleLocator(tick_interval))
    ax.grid(axis="y", linestyle="--", alpha=0.45)

    legend_handles = [
        Patch(facecolor=colors[file_name], edgecolor="white", label=file_name)
        for file_name in file_order
    ]
    legend_labels = [handle.get_label() for handle in legend_handles]

    annotate_missing_cases(
        ax, missing, colors, file_order, legend_handles, legend_labels
    )

    ax.legend(
        legend_handles,
        legend_labels,
        title="File",
        bbox_to_anchor=(1.01, 1),
        loc="upper left",
    )

    plt.tight_layout()
    if output:
        plt.savefig(output, bbox_inches="tight")
        print(f"Plot saved to {output}")
    else:
        plt.show()
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visualize per-case benchmark durations."
    )
    parser.add_argument(
        "--files", nargs="+", required=True, help="One or more benchmark JSON files."
    )
    parser.add_argument(
        "--output", help="Optional path to save the plot (e.g., durations.png)."
    )
    parser.add_argument("--title", help="Optional title override for the plot.")
    parser.add_argument(
        "--summary", action="store_true", help="Print summary statistics per file."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    sns.set_theme(style="white")

    dataframes: List[pl.DataFrame] = []
    for file_path in args.files:
        if not os.path.exists(file_path):
            print(f"Warning: file not found -> {file_path}")
            continue
        df = process_file(file_path)
        if df.is_empty():
            print(f"Warning: no duration data in -> {file_path}")
            continue
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
    colors = build_color_map(file_order)

    if len(dataframes) == 1:
        plot_single_file(dataframes[0], colors, args.title, args.output)
    else:
        plot_layered_files(dataframes, colors, args.title, args.output)


if __name__ == "__main__":
    main()
