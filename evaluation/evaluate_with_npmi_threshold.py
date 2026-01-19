#!/usr/bin/env python3

import argparse
import os
import sys
from typing import Dict, List, Set, Tuple

import matplotlib.pyplot as plt
import numpy as np

# Add the project root directory to sys.path to allow imports from the evaluation package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.utils import get_short_filename, load_groundtruth, load_results


def merge_mappings_by_threshold(
    base_mappings: List[Dict], enhancement_mappings: List[Dict], threshold: float
) -> List[Dict]:
    """
    Merge mappings: for each r_val, if base NPMI < threshold use enhancement mapping,
    otherwise use base mapping. Enhancement may have different s_val choices.
    """
    merged = []

    # Create lookup for enhancement mappings by r_val only
    # (enhancement may have different s_val choices for the same r_val)
    enhancement_lookup = {}
    for m in enhancement_mappings:
        if "r_val" in m:
            r_val_key = m["r_val"].lower().strip()
            enhancement_lookup[r_val_key] = m

    # Track which r_vals we've processed
    processed_r_vals = set()

    # Process base mappings
    for base_m in base_mappings:
        if "r_val" not in base_m:
            continue

        r_val_key = base_m["r_val"].lower().strip()
        processed_r_vals.add(r_val_key)

        npmi = base_m.get("npmi", 0.0)

        if npmi < threshold:
            # NPMI is below threshold, use enhancement if available
            if r_val_key in enhancement_lookup:
                merged.append(enhancement_lookup[r_val_key])
            else:
                # No enhancement available, keep base
                merged.append(base_m)
        else:
            # NPMI is high enough, keep base
            merged.append(base_m)

    # Add any enhancement mappings for r_vals not in base
    for enh_m in enhancement_mappings:
        if "r_val" in enh_m:
            r_val_key = enh_m["r_val"].lower().strip()
            if r_val_key not in processed_r_vals:
                merged.append(enh_m)

    return merged


def calculate_case_metrics(
    groundtruth: Set[Tuple[str, str]], results: List[Dict]
) -> Dict:
    """
    Calculate metrics using ALL mappings (no threshold filtering).
    """
    result_mappings = set()
    for m in results:
        if "r_val" in m and "s_val" in m:
            result_mappings.add(
                (m["r_val"].lower().strip(), m["s_val"].lower().strip())
            )

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
    }


def process_file_pair(
    base_file_path: str, enhancement_file_path: str, groundtruth_dir: str
) -> Tuple[str, Dict[float, Dict]]:
    """
    Process a pair of files across replacement thresholds (0.1 to 1.0).
    For each threshold, merge mappings and calculate metrics using all results.
    Returns filename and dict mapping threshold -> {precision, recall, f1, case_count}
    """
    base_results = load_results(base_file_path)
    enhancement_results = load_results(enhancement_file_path)

    base_filename = get_short_filename(base_file_path)

    enhancement_data = {res.get("case_number"): res for res in enhancement_results}

    # Thresholds for replacement (0.1 to 1.0)
    replacement_thresholds = [round(t, 1) for t in np.arange(0.1, 1.1, 0.1)]
    threshold_results = {}

    for threshold in replacement_thresholds:
        precisions = []
        recalls = []
        f1_scores = []
        case_count = 0

        for case in base_results:
            case_num = case["case_number"]
            gt_file = os.path.join(groundtruth_dir, f"Case{case_num}_groundtruth.txt")

            if not os.path.exists(gt_file):
                continue

            gt_mappings = load_groundtruth(gt_file)
            if not gt_mappings:
                continue

            base_mappings = case.get("output", {}).get("mappings", [])

            # Get enhancement mappings if available
            if case_num in enhancement_data:
                enhancement_case = enhancement_data[case_num]
                enhancement_mappings = enhancement_case.get("output", {}).get(
                    "mappings", []
                )
                # Merge with current threshold
                merged_mappings = merge_mappings_by_threshold(
                    base_mappings, enhancement_mappings, threshold
                )
            else:
                merged_mappings = base_mappings

            # Calculate metrics using all merged mappings
            metrics = calculate_case_metrics(gt_mappings, merged_mappings)
            precisions.append(metrics["precision"])
            recalls.append(metrics["recall"])
            f1_scores.append(metrics["f1"])
            case_count += 1

        # Calculate median metrics for this threshold
        if precisions:
            threshold_results[threshold] = {
                "precision": np.median(precisions),
                "recall": np.median(recalls),
                "f1": np.median(f1_scores),
                "case_count": case_count,
            }

    return base_filename, threshold_results


def create_plot(
    filename: str, threshold_results: Dict[float, Dict], output_dir: str
) -> None:
    """
    Create a line plot showing metrics across replacement thresholds.
    """
    thresholds = sorted(threshold_results.keys())

    precisions = [threshold_results[t]["precision"] for t in thresholds]
    recalls = [threshold_results[t]["recall"] for t in thresholds]
    f1_scores = [threshold_results[t]["f1"] for t in thresholds]
    case_counts = [threshold_results[t]["case_count"] for t in thresholds]

    # Create figure with two y-axes
    fig, ax1 = plt.subplots(figsize=(12, 7))

    # Plot metrics on primary y-axis
    (line1,) = ax1.plot(
        thresholds,
        precisions,
        marker="o",
        linewidth=2,
        label="Precision",
        color="blue",
    )
    (line2,) = ax1.plot(
        thresholds, recalls, marker="s", linewidth=2, label="Recall", color="green"
    )
    (line3,) = ax1.plot(
        thresholds,
        f1_scores,
        marker="^",
        linewidth=2,
        label="F1 Score",
        color="red",
    )

    ax1.set_xlabel("Replacement Threshold (NPMI)", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Metric Score", fontsize=12, fontweight="bold", color="black")
    ax1.set_ylim([0, 1.05])
    ax1.set_xticks(thresholds)
    ax1.grid(True, alpha=0.3)
    ax1.tick_params(axis="y", labelcolor="black")

    # Create secondary y-axis for case count
    ax2 = ax1.twinx()
    (line4,) = ax2.plot(
        thresholds,
        case_counts,
        marker="d",
        linewidth=2,
        label="Cases Evaluated",
        color="purple",
        linestyle="--",
    )
    ax2.set_ylabel("Number of Cases", fontsize=12, fontweight="bold", color="purple")
    ax2.tick_params(axis="y", labelcolor="purple")

    # Combine legends from both axes
    lines = [line1, line2, line3, line4]
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="center left", fontsize=10)

    plt.title(f"Base vs Enhancement Mix - {filename}", fontsize=14, fontweight="bold")
    plt.tight_layout()

    # Save plot
    output_filename = f"npmi_threshold_analysis_{filename}.png"
    output_path = os.path.join(output_dir, output_filename)
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    print(f"  Plot saved to {output_path}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Analyze optimal mix of base and enhancement benchmark results. "
        "Creates one plot per file pair showing how metrics change as replacement threshold increases."
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
        "benchmark_files",
        nargs="+",
        help="Pairs of benchmark files: base enhancement base enhancement ...",
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
    print(f"Replacement thresholds: 0.1 to 1.0 in steps of 0.1")
    print()

    # Parse file pairs
    if len(args.benchmark_files) % 2 != 0:
        print(
            "Error: Please provide an even number of files (pairs of base and enhancement files)."
        )
        return

    file_pairs = []
    for i in range(0, len(args.benchmark_files), 2):
        base_file = args.benchmark_files[i]
        enhancement_file = args.benchmark_files[i + 1]
        file_pairs.append((base_file, enhancement_file))

    # Process each file pair
    for base_file, enhancement_file in file_pairs:
        if not os.path.exists(base_file):
            print(f"Warning: Base file {base_file} not found. Skipping.")
            continue

        if not os.path.exists(enhancement_file):
            print(f"Warning: Enhancement file {enhancement_file} not found. Skipping.")
            continue

        print(f"Processing pair:")
        print(f"  Base:       {base_file}")
        print(f"  Enhancement: {enhancement_file}")

        filename, threshold_results = process_file_pair(
            base_file, enhancement_file, args.groundtruth_dir
        )

        # Verify we have data
        if not threshold_results:
            print(f"  Warning: No valid data found for this pair")
            continue

        print(f"  Creating plot...")
        create_plot(filename, threshold_results, args.output_dir)
        print()


if __name__ == "__main__":
    main()
