#!/usr/bin/env python3

import argparse
import os
import sys
from typing import Dict, List, Set, Tuple

import matplotlib.pyplot as plt
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.utils import get_short_filename, load_groundtruth, load_results


def merge_mappings_by_threshold(
    base_mappings: List[Dict], enhancement_mappings: List[Dict], threshold: float
) -> Tuple[List[Dict], Dict[str, int]]:
    """
    Merge mappings: for each r_val, keep only the first occurrence from base (highest NPMI).
    If that mapping's NPMI < threshold, use enhancement mapping instead.
    Returns merged mappings and debug stats.
    """
    merged = []
    stats = {
        "base_kept": 0,
        "base_replaced": 0,
        "base_no_enhancement": 0,
        "enhancement_only": 0,
        "base_duplicates_skipped": 0,
    }

    enhancement_lookup = {}
    for m in enhancement_mappings:
        if "r_val" in m:
            r_val_key = m["r_val"].lower().strip()
            if r_val_key not in enhancement_lookup:
                enhancement_lookup[r_val_key] = m

    processed_r_vals = set()

    for base_m in base_mappings:
        if "r_val" not in base_m:
            continue

        r_val_key = base_m["r_val"].lower().strip()

        # Skip if we've already processed this r_val (for top_k_5 files)
        if r_val_key in processed_r_vals:
            stats["base_duplicates_skipped"] += 1
            continue

        processed_r_vals.add(r_val_key)

        npmi = base_m.get("npmi", 0.0)

        if npmi < threshold:
            if r_val_key in enhancement_lookup:
                merged.append(enhancement_lookup[r_val_key])
                stats["base_replaced"] += 1
            else:
                # No enhancement available, keep base
                merged.append(base_m)
                stats["base_no_enhancement"] += 1
        else:
            merged.append(base_m)
            stats["base_kept"] += 1

    for enh_m in enhancement_mappings:
        if "r_val" in enh_m:
            r_val_key = enh_m["r_val"].lower().strip()
            if r_val_key not in processed_r_vals:
                merged.append(enh_m)
                stats["enhancement_only"] += 1

    return merged, stats


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

    replacement_thresholds = [round(t, 1) for t in np.arange(0.1, 1.1, 0.1)]
    threshold_results = {}

    for threshold in replacement_thresholds:
        precisions = []
        recalls = []
        f1_scores = []
        case_count = 0

        total_stats = {
            "base_kept": 0,
            "base_replaced": 0,
            "base_no_enhancement": 0,
            "enhancement_only": 0,
            "base_duplicates_skipped": 0,
        }

        for case in base_results:
            case_num = case["case_number"]
            gt_file = os.path.join(groundtruth_dir, f"Case{case_num}_groundtruth.txt")

            if not os.path.exists(gt_file):
                continue

            gt_mappings = load_groundtruth(gt_file)
            if not gt_mappings:
                continue

            base_mappings = case.get("output", {}).get("mappings", [])

            if case_num in enhancement_data:
                enhancement_case = enhancement_data[case_num]
                enhancement_mappings = enhancement_case.get("output", {}).get(
                    "mappings", []
                )
                merged_mappings, stats = merge_mappings_by_threshold(
                    base_mappings, enhancement_mappings, threshold
                )
                for key in total_stats:
                    total_stats[key] += stats[key]
            else:
                merged_mappings = base_mappings

            metrics = calculate_case_metrics(gt_mappings, merged_mappings)
            precisions.append(metrics["precision"])
            recalls.append(metrics["recall"])
            f1_scores.append(metrics["f1"])
            case_count += 1

        if precisions:
            threshold_results[threshold] = {
                "precision": np.median(precisions),
                "recall": np.median(recalls),
                "f1": np.median(f1_scores),
                "case_count": case_count,
                "debug_stats": total_stats,
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

    fig, ax1 = plt.subplots(figsize=(12, 7))

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

    lines = [line1, line2, line3, line4]
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="center left", fontsize=10)

    plt.title(f"Base vs Enhancement Mix - {filename}", fontsize=14, fontweight="bold")
    plt.tight_layout()

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

    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
        print(f"Created output directory: {args.output_dir}")

    print(f"Groundtruth directory: {args.groundtruth_dir}")
    print(f"Output directory: {args.output_dir}")
    print(f"Replacement thresholds: 0.1 to 1.0 in steps of 0.1")
    print()

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

    for base_file, enhancement_file in file_pairs:
        if not os.path.exists(base_file):
            print(f"Warning: Base file {base_file} not found. Skipping.")
            continue

        if not os.path.exists(enhancement_file):
            print(f"Warning: Enhancement file {enhancement_file} not found. Skipping.")
            continue

        print(f"Processing pair:")
        print(f"  Base:        {base_file}")
        print(f"  Enhancement: {enhancement_file}")

        filename, threshold_results = process_file_pair(
            base_file, enhancement_file, args.groundtruth_dir
        )

        if not threshold_results:
            print(f"  Warning: No valid data found for this pair")
            continue

        print(f"\n  Debug info:")
        for threshold in [0.1, 1.0]:
            if threshold in threshold_results:
                result = threshold_results[threshold]
                stats = result.get("debug_stats", {})
                print(f"    Threshold {threshold}:")
                print(f"      Base kept: {stats.get('base_kept', 0)}")
                print(f"      Base replaced: {stats.get('base_replaced', 0)}")
                print(
                    f"      Base no enhancement: {stats.get('base_no_enhancement', 0)}"
                )
                print(f"      Enhancement only: {stats.get('enhancement_only', 0)}")
                print(
                    f"      Duplicates skipped: {stats.get('base_duplicates_skipped', 0)}"
                )
                print(
                    f"      Metrics - P: {result['precision']:.4f}, R: {result['recall']:.4f}, F1: {result['f1']:.4f}"
                )

        print(f"\n  Creating plot...")
        create_plot(filename, threshold_results, args.output_dir)
        print()


if __name__ == "__main__":
    main()
