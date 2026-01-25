import argparse
import os
import sys
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.patches import Patch

# Add the project root directory to sys.path to allow imports from the evaluation package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.plot_style import apply_theme, build_styles, save_figure
from evaluation.utils import (
    calculate_case_metrics,
    get_short_filename,
    load_groundtruth,
    load_results,
)


def process_file(file_path: str, groundtruth_dir: str) -> Tuple[str, pl.DataFrame]:
    results_data = load_results(file_path)
    filename = get_short_filename(file_path)

    eval_data = []

    for case in results_data:
        case_num = case["case_number"]
        gt_file = os.path.join(groundtruth_dir, f"Case{case_num}_groundtruth.txt")

        if not os.path.exists(gt_file):
            print(f"Warning: Groundtruth file {gt_file} not found for case {case_num}.")
            continue

        gt_mappings = load_groundtruth(gt_file)
        if not gt_mappings:
            # print(f"Warning: No mappings found in groundtruth for case {case_num}.")
            pass

        metrics = calculate_case_metrics(
            gt_mappings, case.get("output", {}).get("mappings", [])
        )

        metrics["case"] = case_num
        metrics["file"] = filename
        metrics["duration"] = case.get("duration_seconds", 0.0)
        eval_data.append(metrics)

    if not eval_data:
        return filename, pl.DataFrame()

    return filename, pl.DataFrame(eval_data)


def get_median_metrics(df: pl.DataFrame) -> Dict[str, float]:
    if df.is_empty():
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    return {
        "precision": float(df["precision"].median() or 0.0),
        "recall": float(df["recall"].median() or 0.0),
        "f1": float(df["f1"].median() or 0.0),
    }


def plot_absolute_values(
    results: List[Dict[str, float | str]], output_file: str = None
):
    metrics = ["Precision", "Recall", "F1"]
    filenames = [str(r["file"]) for r in results]

    styles = build_styles(filenames)

    fig, ax = plt.subplots(figsize=(12, 6))

    n_files = len(filenames)
    n_metrics = len(metrics)

    total_width = 0.8
    bar_width = total_width / n_files
    indices = np.arange(n_metrics)

    for i, file_data in enumerate(results):
        filename = str(file_data["file"])
        values = [
            float(file_data["precision"]),
            float(file_data["recall"]),
            float(file_data["f1"]),
        ]

        positions = indices - (total_width / 2) + (i * bar_width) + (bar_width / 2)
        style = styles[filename]

        ax.bar(
            positions,
            values,
            width=bar_width,
            label=filename,
            color=style["facecolor"],
            edgecolor=style["edgecolor"],
            hatch=style["hatch"],
            alpha=style["alpha"],
        )

    ax.set_xticks(indices)
    ax.set_xticklabels(metrics)
    ax.set_ylabel("Score")
    ax.set_title("Absolute Metrics Comparison")
    ax.set_ylim(0, 1.05)

    legend_handles = [
        Patch(
            facecolor=styles[f]["facecolor"],
            edgecolor=styles[f]["edgecolor"],
            hatch=styles[f]["hatch"],
            label=f,
        )
        for f in filenames
    ]
    ax.legend(
        legend_handles,
        filenames,
        title="Files",
        bbox_to_anchor=(1.05, 1),
        loc="upper left",
    )

    plt.tight_layout()

    if output_file:
        save_figure(output_file)
    else:
        plt.show()


def plot_comparison(
    baseline_name: str,
    diffs: List[Dict[str, float | str]],
    is_percentage: bool,
    output_file: str = None,
):
    metrics = ["Precision", "Recall", "F1"]

    unique_files = sorted(list({str(d["file"]) for d in diffs}))
    styles = build_styles(unique_files)

    fig, ax = plt.subplots(figsize=(10, 6))

    bar_width = 0.5
    indices = np.arange(len(metrics))

    # For each metric, we need to stack bars
    # We separate positive and negative values
    # Sort by absolute value ascending (closest to 0 first)

    for i, metric in enumerate(metrics):
        # Get all diffs for this metric
        metric_diffs = []
        for d in diffs:
            metric_diffs.append((str(d["file"]), float(d[metric])))

        # Re-sort all diffs by absolute value descending
        metric_diffs.sort(key=lambda x: abs(x[1]), reverse=True)

        for filename, val in metric_diffs:
            style = styles[filename]
            ax.bar(
                indices[i],
                val,
                width=bar_width,
                color=style["facecolor"],
                edgecolor=style["edgecolor"],
                hatch=style["hatch"],
                alpha=style["alpha"],
                label=filename if i == 0 else "",
            )

    ax.set_xticks(indices)
    ax.set_xticklabels(metrics)

    ylabel = "Difference to Baseline (Median)"
    if is_percentage:
        ylabel = "Percentage Difference to Baseline (Median)"
        from matplotlib.ticker import FuncFormatter

        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.0f}%"))

    ax.set_ylabel(ylabel)
    ax.set_title(f"Comparison of Benchmark Results vs Baseline: {baseline_name}")
    ax.axhline(0, color="black", linewidth=0.8)

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
        title="Comparison Files",
        bbox_to_anchor=(1.05, 1),
        loc="upper left",
    )

    plt.tight_layout()

    if output_file:
        save_figure(output_file)
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Compare benchmark results against a baseline."
    )
    parser.add_argument(
        "--baseline", required=True, help="Path to the baseline result file"
    )
    parser.add_argument(
        "--comparisons",
        nargs="+",
        required=True,
        help="Paths to comparison result files",
    )
    parser.add_argument(
        "--groundtruth_dir",
        default="benchmark-data",
        help="Directory containing groundtruth files",
    )
    parser.add_argument("--output", help="Output file for plot (e.g., comparison.png)")
    parser.add_argument(
        "--percentage", action="store_true", help="Use percentage based differences"
    )
    parser.add_argument(
        "--absolute",
        action="store_true",
        help="Plot absolute values instead of differences",
    )

    args = parser.parse_args()
    apply_theme()

    if not os.path.exists(args.groundtruth_dir):
        print(f"Error: Groundtruth directory {args.groundtruth_dir} does not exist.")
        return

    if args.absolute:
        results = []
        # Load Baseline
        print(f"Loading baseline: {args.baseline}")
        baseline_name, baseline_df = process_file(args.baseline, args.groundtruth_dir)
        if not baseline_df.is_empty():
            m = get_median_metrics(baseline_df)
            m["file"] = str(baseline_name)
            results.append(m)
        else:
            print("Warning: Baseline data is empty.")

        # Load Comparisons
        for comp_path in args.comparisons:
            print(f"Loading comparison: {comp_path}")
            comp_name, comp_df = process_file(comp_path, args.groundtruth_dir)
            if comp_df.is_empty():
                print(f"Warning: Comparison data for {comp_path} is empty. Skipping.")
                continue

            m = get_median_metrics(comp_df)
            m["file"] = str(comp_name)
            results.append(m)

        if not results:
            print("No valid data found.")
            return

        plot_absolute_values(results, args.output)
        return

    # Load Baseline
    print(f"Loading baseline: {args.baseline}")
    baseline_name, baseline_df = process_file(args.baseline, args.groundtruth_dir)
    if baseline_df.is_empty():
        print("Error: Baseline data is empty.")
        return

    baseline_metrics = get_median_metrics(baseline_df)
    print(f"Baseline ({baseline_name}) metrics: {baseline_metrics}")

    # Load Comparisons
    diffs = []
    for comp_path in args.comparisons:
        print(f"Loading comparison: {comp_path}")
        comp_name, comp_df = process_file(comp_path, args.groundtruth_dir)
        if comp_df.is_empty():
            print(f"Warning: Comparison data for {comp_path} is empty. Skipping.")
            continue

        comp_metrics = get_median_metrics(comp_df)

        comp_name_str = str(comp_name)
        if args.percentage:
            diff: Dict[str, float | str] = {
                "file": comp_name_str,
                "Precision": (
                    float(comp_metrics["precision"]) - baseline_metrics["precision"]
                )
                / baseline_metrics["precision"]
                * 100
                if baseline_metrics["precision"] != 0
                else 0.0,
                "Recall": (float(comp_metrics["recall"]) - baseline_metrics["recall"])
                / baseline_metrics["recall"]
                * 100
                if baseline_metrics["recall"] != 0
                else 0.0,
                "F1": (float(comp_metrics["f1"]) - baseline_metrics["f1"])
                / baseline_metrics["f1"]
                * 100
                if baseline_metrics["f1"] != 0
                else 0.0,
            }
        else:
            diff = {
                "file": comp_name_str,
                "Precision": float(comp_metrics["precision"])
                - baseline_metrics["precision"],
                "Recall": float(comp_metrics["recall"]) - baseline_metrics["recall"],
                "F1": float(comp_metrics["f1"]) - baseline_metrics["f1"],
            }
        diffs.append(diff)

    if not diffs:
        print("No valid comparison data found.")
        return

    plot_comparison(baseline_name, diffs, args.percentage, args.output)


if __name__ == "__main__":
    main()
