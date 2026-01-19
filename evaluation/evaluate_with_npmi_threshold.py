#!/usr/bin/env python3

import argparse
import os
import sys
from typing import Dict, List, Set, Tuple

import matplotlib.pyplot as plt
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.utils import get_short_filename, load_groundtruth, load_results


def calculate_case_metrics_with_threshold(
    groundtruth: Set[Tuple[str, str]], results: List[Dict], npmi_threshold: float
) -> Tuple[Dict, bool]:
    """
    Calculate metrics considering only mappings with NPMI score above threshold.
    Returns metrics dict and a boolean indicating if any mappings passed the filter.
    """
    result_mappings = set()
    for m in results:
        if "r_val" in m and "s_val" in m:
            # Check if NPMI score meets threshold
            npmi = m.get("npmi", 0.0)
            if npmi >= npmi_threshold:
                result_mappings.add(
                    (m["r_val"].lower().strip(), m["s_val"].lower().strip())
                )

    # Return 0 metrics and False if no mappings passed filter
    if not result_mappings:
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "tp": 0,
            "fp": 0,
            "fn": len(groundtruth),
        }, False

    tp = len(groundtruth.intersection(result_mappings))
    fp = len(result_mappings - groundtruth)
    fn = len(groundtruth - result_mappings)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }, True


def process_file_with_thresholds(
    file_path: str, groundtruth_dir: str
) -> Tuple[str, Dict[float, Dict]]:
    """
    Process a benchmark file and calculate metrics for each NPMI threshold.
    Returns filename and a dict mapping threshold -> {metrics, cases_with_mappings}
    """
    results_data = load_results(file_path)
    filename = get_short_filename(file_path)

    thresholds = [float(round(t, 1)) for t in np.arange(0.1, 1.1, 0.1)]
    threshold_results = {
        t: {"metrics": [], "cases_with_mappings": 0} for t in thresholds
    }

    for case in results_data:
        case_num = case["case_number"]
        gt_file = os.path.join(groundtruth_dir, f"Case{case_num}_groundtruth.txt")

        if not os.path.exists(gt_file):
            continue

        gt_mappings = load_groundtruth(gt_file)
        if not gt_mappings:
            continue

        case_mappings = case.get("output", {}).get("mappings", [])

        for threshold in thresholds:
            metrics, had_mappings = calculate_case_metrics_with_threshold(
                gt_mappings, case_mappings, threshold
            )
            threshold_results[threshold]["metrics"].append(metrics)
            if had_mappings:
                threshold_results[threshold]["cases_with_mappings"] += 1

    return filename, threshold_results


def calculate_aggregated_metrics(
    metrics_list: List[Dict],
) -> Dict[str, float]:
    """
    Calculate median metrics from a list of case metrics.
    """
    if not metrics_list:
        return {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        }

    precisions = [m["precision"] for m in metrics_list]
    recalls = [m["recall"] for m in metrics_list]
    f1_scores = [m["f1"] for m in metrics_list]

    return {
        "precision": np.median(precisions),
        "recall": np.median(recalls),
        "f1": np.median(f1_scores),
    }


def create_plot(
    filename: str,
    threshold_results: Dict[float, Dict],
    output_dir: str,
) -> None:
    """
    Create a line plot showing metrics and case count across NPMI thresholds.
    """
    thresholds = sorted(threshold_results.keys())

    precisions = []
    recalls = []
    f1_scores = []
    cases_counts = []

    for threshold in thresholds:
        data = threshold_results[threshold]
        metrics = calculate_aggregated_metrics(data["metrics"])
        precisions.append(metrics["precision"])
        recalls.append(metrics["recall"])
        f1_scores.append(metrics["f1"])
        cases_counts.append(data["cases_with_mappings"])

    _, ax1 = plt.subplots(figsize=(12, 7))

    (line1,) = ax1.plot(
        thresholds, precisions, marker="o", linewidth=2, label="Precision", color="blue"
    )
    (line2,) = ax1.plot(
        thresholds, recalls, marker="s", linewidth=2, label="Recall", color="green"
    )
    (line3,) = ax1.plot(
        thresholds, f1_scores, marker="^", linewidth=2, label="F1 Score", color="red"
    )

    ax1.set_xlabel("NPMI Threshold", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Metric Score", fontsize=12, fontweight="bold", color="black")
    ax1.set_ylim((0, 1.05))
    ax1.set_xticks(thresholds)
    ax1.grid(True, alpha=0.3)
    ax1.tick_params(axis="y", labelcolor="black")

    ax2 = ax1.twinx()
    (line4,) = ax2.plot(
        thresholds,
        cases_counts,
        marker="d",
        linewidth=2,
        label="Cases with Mappings",
        color="purple",
        linestyle="--",
    )
    ax2.set_ylabel("Number of Cases", fontsize=12, fontweight="bold", color="purple")
    ax2.tick_params(axis="y", labelcolor="purple")

    # Combine legends from both axes
    lines = [line1, line2, line3, line4]
    labels = [line.get_label() for line in lines]
    ax1.legend(lines, labels, loc="center left", fontsize=10)

    plt.title(f"Metrics vs NPMI Threshold - {filename}", fontsize=14, fontweight="bold")
    plt.tight_layout()

    # Save plot with filename based on input
    output_filename = f"npmi_threshold_analysis_{filename}.png"
    output_path = os.path.join(output_dir, output_filename)
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"Plot saved to {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze benchmark files across NPMI thresholds and create plots."
    )
    parser.add_argument(
        "--groundtruth_dir",
        default="benchmark-data",
        help="Directory containing groundtruth files",
    )
    parser.add_argument(
        "--output_dir",
        default="evaluation/plots",
        help="Directory to save output plots",
    )
    parser.add_argument(
        "benchmark_files", nargs="+", help="Paths to benchmark result files"
    )

    args = parser.parse_args()

    if not os.path.exists(args.groundtruth_dir):
        print(f"Error: Groundtruth directory {args.groundtruth_dir} does not exist.")
        return

    # Create output directory if it doesn't exist
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
        print(f"Created output directory: {args.output_dir}")

    print(f"Groundtruth directory: {args.groundtruth_dir}")
    print(f"Output directory: {args.output_dir}")
    print()

    for benchmark_file in args.benchmark_files:
        if not os.path.exists(benchmark_file):
            print(f"Warning: Benchmark file {benchmark_file} not found. Skipping.")
            continue

        print(f"Processing: {benchmark_file}")
        filename, threshold_results = process_file_with_thresholds(
            benchmark_file, args.groundtruth_dir
        )

        # Verify we have data
        has_data = any(len(data["metrics"]) > 0 for data in threshold_results.values())
        if not has_data:
            print(f"  Warning: No valid data found for {filename}")
            continue

        print("  Creating plot...")
        create_plot(filename, threshold_results, args.output_dir)
        print()


if __name__ == "__main__":
    main()
