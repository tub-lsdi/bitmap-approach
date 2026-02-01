import argparse
import os
import sys
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import polars as pl
import seaborn as sns
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.plot_style import apply_theme, build_styles, save_figure
from evaluation.utils import (
    calculate_case_metrics,
    get_short_filename,
    load_groundtruth,
    load_results,
)


def process_file(
    file_path: str, groundtruth_dir: str, file_label: str | None = None
) -> pl.DataFrame:
    results_data = load_results(file_path)
    filename = file_label if file_label is not None else get_short_filename(file_path)

    eval_data = []

    for case in results_data:
        case_num = case["case_number"]
        gt_file = os.path.join(groundtruth_dir, f"Case{case_num}_groundtruth.txt")

        if not os.path.exists(gt_file):
            print(f"Warning: Groundtruth file {gt_file} not found for case {case_num}.")
            continue

        gt_mappings = load_groundtruth(gt_file)
        if not gt_mappings:
            print(f"Warning: No mappings found in groundtruth for case {case_num}.")

        metrics = calculate_case_metrics(
            gt_mappings, case.get("output", {}).get("mappings", [])
        )

        metrics["case"] = case_num
        metrics["file"] = filename
        metrics["duration"] = case.get("duration_seconds", 0.0)
        eval_data.append(metrics)

    if not eval_data:
        return pl.DataFrame()

    return pl.DataFrame(eval_data)


def plot_single_file(
    df: pl.DataFrame, styles: Dict[str, Dict[str, Any]], output_file: str | None = None
):
    if df.is_empty():
        print("No data to plot.")
        return

    pdf = df.to_pandas()
    file_name = pdf["file"].iloc[0]
    style = styles[file_name]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.bar(
        pdf["case"],
        pdf["f1"],
        color=style["facecolor"],
        edgecolor=style["edgecolor"],
        hatch=style["hatch"],
        alpha=style["alpha"],
    )
    ax.set_title(f"F1 Score per Case - {file_name}")
    ax.set_xlabel("Case Number")
    ax.set_ylabel("F1 Score")
    ax.set_xticks(pdf["case"])
    ax.set_xticklabels(pdf["case"], rotation=45)
    ax.set_ylim(0, 1.05)

    legend_handle = Patch(
        facecolor=style["facecolor"],
        edgecolor=style["edgecolor"],
        hatch=style["hatch"],
        label=file_name,
    )
    ax.legend(
        handles=[legend_handle],
        title="Legend",
        bbox_to_anchor=(1.01, 1),
        loc="upper left",
    )

    plt.tight_layout()

    if output_file:
        save_figure(output_file)
    else:
        plt.show()


def plot_bar_comparison(
    dfs: List[pl.DataFrame],
    styles: Dict[str, Dict[str, Any]],
    output_file: str | None = None,
    show_table: bool = True,
):
    if not dfs:
        print("No data to compare.")
        return

    combined_df = pl.concat(dfs)
    if combined_df.is_empty():
        print("Combined data is empty.")
        return

    # Calculate summary stats
    summary_df = combined_df.group_by("file", maintain_order=True).agg(
        [
            pl.col("precision").mean().alias("Precision"),
            pl.col("recall").mean().alias("Recall"),
            pl.col("f1").mean().alias("F1"),
            pl.col("duration").median().alias("Duration (s)"),
        ]
    )

    unique_files = [str(f) for f in summary_df["file"].to_list()]
    file_palette = {f: styles[f]["facecolor"] for f in unique_files}

    # Convert to pandas for plotting
    plot_data = combined_df.to_pandas()
    summary_data = summary_df.to_pandas()

    cell_text = []
    row_colors = []

    for _, row in summary_data.iterrows():
        filename = str(row["file"])
        r = [""]
        r.append(f"{row['Precision']:.3f}")
        r.append(f"{row['Recall']:.3f}")
        r.append(f"{row['F1']:.3f}")
        r.append(f"{row['Duration (s)']:.2f}")
        cell_text.append(r)
        row_colors.append(styles[filename]["facecolor"])

    col_labels = ["File", "Precision", "Recall", "F1", "Duration (s)"]

    fig_width = 20 if show_table else 14
    fig, ax = plt.subplots(figsize=(fig_width, 8))

    sns.barplot(
        data=plot_data, x="case", y="f1", hue="file", ax=ax, palette=file_palette
    )
    ax.set_title("F1 Score Comparison per Case")
    ax.set_xlabel("Case Number")
    ax.set_ylabel("F1 Score")

    try:
        xticks = ax.get_xticks().tolist()
    except Exception:
        xticks = [float(x) for x in ax.get_xticks()]
    ax.xaxis.set_major_locator(ticker.FixedLocator(xticks))
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45)

    ax.set_ylim(0, 1.05)

    if unique_files:
        num_files = len(unique_files)
        for idx, patch in enumerate(ax.patches):
            file_idx = idx % num_files
            fname = unique_files[file_idx]
            patch.set_hatch(styles[fname]["hatch"])
            patch.set_edgecolor(styles[fname]["edgecolor"])
            patch.set_alpha(styles[fname]["alpha"])

    legend_handles = [
        Patch(
            facecolor=styles[f]["facecolor"],
            edgecolor=styles[f]["edgecolor"],
            hatch=styles[f]["hatch"],
            label=f,
        )
        for f in unique_files
    ]
    ax.legend(
        legend_handles,
        unique_files,
        title="Legend",
        bbox_to_anchor=(1.01, 1),
        loc="upper left",
    )

    if show_table:
        plt.subplots_adjust(right=0.65)

        table = plt.table(
            cellText=cell_text,
            colLabels=col_labels,
            loc="right",
            bbox=[1.02, 0.4, 0.45, 0.3],
        )

        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.5)

        for i, color in enumerate(row_colors):
            cell = table[i + 1, 0]
            cell.set_facecolor(color)
    else:
        plt.tight_layout()

    if output_file:
        save_figure(output_file)
    else:
        plt.show()


def plot_heatmap(
    dfs: List[pl.DataFrame],
    styles: Dict[str, Dict[str, Any]],
    output_file: str | None = None,
    show_table: bool = True,
):
    if not dfs:
        print("No data to plot.")
        return

    combined_df = pl.concat(dfs)
    if combined_df.is_empty():
        print("Combined data is empty.")
        return

    # Calculate summary stats for table
    summary_df = combined_df.group_by("file", maintain_order=True).agg(
        [
            pl.col("precision").mean().alias("Precision"),
            pl.col("recall").mean().alias("Recall"),
            pl.col("f1").mean().alias("F1"),
            pl.col("duration").median().alias("Duration (s)"),
        ]
    )

    summary_data = summary_df.to_pandas()
    cell_text: List[List[str]] = []
    row_colors: List[Any] = []

    for _, row in summary_data.iterrows():
        file_label = str(row["file"])
        r = [file_label]
        r.append(f"{row['Precision']:.3f}")
        r.append(f"{row['Recall']:.3f}")
        r.append(f"{row['F1']:.3f}")
        duration = row.get("Duration (s)", 0.0)
        try:
            if duration is None or duration != duration:
                duration = 0.0
        except Exception:
            duration = 0.0
        r.append(f"{float(duration):.2f}")
        cell_text.append(r)
        row_colors.append(styles.get(file_label, {}).get("facecolor"))

    col_labels = ["File", "Precision", "Recall", "F1", "Duration (s)"]

    pivot_df = combined_df.pivot(
        values="f1", index="file", on="case", aggregate_function="first"
    )

    pandas_df = pivot_df.to_pandas()
    pandas_df.set_index("file", inplace=True)

    try:
        sorted_cols = sorted(pandas_df.columns, key=lambda x: int(x))
    except (ValueError, TypeError):
        sorted_cols = sorted(pandas_df.columns)
    pandas_df = pandas_df.reindex(sorted_cols, axis=1)

    # Figure layout
    fig_height = max(3, len(dfs) * 0.4 + 1.5)
    ax_table = None

    if show_table:
        fig = plt.figure(figsize=(24, fig_height))
        gs = GridSpec(1, 2, width_ratios=[4, 2], figure=fig)
        ax_heatmap = fig.add_subplot(gs[0])
        ax_table = fig.add_subplot(gs[1])
        ax_table.axis("off")
    else:
        fig = plt.figure(figsize=(16, fig_height))
        ax_heatmap = fig.add_subplot(111)

    sns.heatmap(
        pandas_df,
        annot=False,
        cmap="RdYlGn",
        fmt=".2f",
        cbar_kws={"label": "F1 Score", "shrink": 0.5},
        ax=ax_heatmap,
        vmin=0,
        vmax=1,
        square=True,
    )

    ax_heatmap.set_title("F1 Score Heatmap per Case")
    ax_heatmap.set_xlabel("Case Number")
    ax_heatmap.set_ylabel("File")

    if show_table and ax_table is not None:
        # Table
        col_widths = [0.4, 0.15, 0.15, 0.15, 0.15]

        table = ax_table.table(
            cellText=cell_text, colLabels=col_labels, colWidths=col_widths, loc="center"
        )
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.5)

        for i, color in enumerate(row_colors):
            if color is not None:
                table[i + 1, 0].set_facecolor(color)

    plt.tight_layout()

    if output_file:
        save_figure(output_file)
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(description="Evaluate benchmark results.")
    parser.add_argument(
        "--groundtruth_dir",
        default="benchmark-data",
        help="Directory containing groundtruth files",
    )
    parser.add_argument(
        "--results_dir", default="", help="Directory containing result files"
    )
    parser.add_argument(
        "--files",
        nargs="+",
        help="Specific result files to evaluate (filenames in results_dir)",
    )
    parser.add_argument(
        "--plot",
        nargs="?",
        const="bar",
        default=None,
        help="Generate plots. Options: 'bar' (default), 'heatmap'",
    )
    parser.add_argument("--output", help="Output file for plot (e.g., plot.png)")
    parser.add_argument(
        "--summary", action="store_true", help="Print summary statistics"
    )
    parser.add_argument(
        "--no-table",
        action="store_true",
        help="Do not show the summary table in the plot",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="FILE=LABEL",
        help=(
            "Override the displayed label for a result file (repeatable, e.g., "
            "results.json=Experiment A)."
        ),
    )

    args = parser.parse_args()

    label_overrides: Dict[str, str] = {}
    for entry in args.label:
        if "=" not in entry:
            print(f"Warning: invalid label override, expected FILE=LABEL -> {entry}")
            continue
        raw_file, custom_label = entry.split("=", 1)
        normalized_file = os.path.normpath(os.path.abspath(raw_file))
        label_overrides[normalized_file] = custom_label

    apply_theme()

    groundtruth_dir = args.groundtruth_dir
    results_dir = (
        args.results_dir if args.results_dir and args.results_dir != "" else os.curdir
    )

    if not os.path.exists(groundtruth_dir):
        print(f"Error: Groundtruth directory {groundtruth_dir} does not exist.")
        return

    if not os.path.exists(results_dir):
        print(f"Error: Results directory {results_dir} does not exist.")
        return

    files_to_process = []
    if args.files:
        for f in args.files:
            files_to_process.append(os.path.join(results_dir, f))
    else:
        for f in os.listdir(results_dir):
            if f.endswith(".json"):
                files_to_process.append(os.path.join(results_dir, f))

    if not files_to_process:
        print("No files to process.")
        return

    dfs = []
    for file_path in files_to_process:
        print(f"Processing {file_path}...")
        normalized_path = os.path.normpath(os.path.abspath(file_path))
        file_label = label_overrides.get(normalized_path)
        df = process_file(file_path, groundtruth_dir, file_label)
        if not df.is_empty():
            dfs.append(df)
            if args.summary:
                summary_label = file_label or get_short_filename(file_path)
                print(f"Summary for {summary_label}:")
                print(
                    df.select(
                        [
                            pl.col("precision").mean().alias("mean_precision"),
                            pl.col("recall").mean().alias("mean_recall"),
                            pl.col("f1").mean().alias("mean_f1"),
                            pl.col("duration").median().alias("mean_duration"),
                        ]
                    )
                )
                print("-" * 40)

    if args.plot and dfs:
        file_labels = [df["file"][0] for df in dfs]
        styles = build_styles(file_labels)
        show_table = not args.no_table
        if args.plot == "heatmap":
            plot_heatmap(dfs, styles, args.output, show_table)
        else:
            if len(dfs) == 1:
                plot_single_file(dfs[0], styles, args.output)
            else:
                plot_bar_comparison(dfs, styles, args.output, show_table)


if __name__ == "__main__":
    main()
