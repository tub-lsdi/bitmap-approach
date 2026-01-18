import argparse
import json
import os
import statistics
import sys
from typing import Dict, List, Set, Tuple

# Add the project root directory to sys.path to allow imports from the evaluation package
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.utils import get_short_filename, load_groundtruth, load_results


def calculate_case_metrics_with_threshold(
    groundtruth: Set[Tuple[str, str]], results: List[Dict], npmi_threshold: float
) -> Dict:
    """
    Calculate metrics considering only mappings with NPMI score above threshold.
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


def process_file(
    file_path: str, groundtruth_dir: str, npmi_threshold: float
) -> Tuple[str, List[Dict]]:
    """
    Process a benchmark file and return metrics for each case filtered by NPMI threshold.
    """
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
            pass

        metrics = calculate_case_metrics_with_threshold(
            gt_mappings, case.get("output", {}).get("mappings", []), npmi_threshold
        )

        metrics["case"] = case_num
        metrics["file"] = filename
        eval_data.append(metrics)

    return filename, eval_data


def calculate_statistics(metrics_list: List[Dict]) -> Dict[str, float]:
    """
    Calculate median and mean for precision, recall, and F1 scores.
    """
    if not metrics_list:
        return {
            "median_precision": 0.0,
            "mean_precision": 0.0,
            "median_recall": 0.0,
            "mean_recall": 0.0,
            "median_f1": 0.0,
            "mean_f1": 0.0,
        }

    precisions = [m["precision"] for m in metrics_list]
    recalls = [m["recall"] for m in metrics_list]
    f1_scores = [m["f1"] for m in metrics_list]

    return {
        "median_precision": statistics.median(precisions),
        "mean_precision": statistics.mean(precisions),
        "median_recall": statistics.median(recalls),
        "mean_recall": statistics.mean(recalls),
        "median_f1": statistics.median(f1_scores),
        "mean_f1": statistics.mean(f1_scores),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate benchmark files with NPMI threshold filtering."
    )
    parser.add_argument(
        "--groundtruth_dir",
        default="benchmark-data",
        help="Directory containing groundtruth files",
    )
    parser.add_argument(
        "--npmi_threshold",
        type=float,
        required=True,
        help="NPMI threshold to filter mappings (float value)",
    )
    parser.add_argument(
        "benchmark_files", nargs="+", help="Paths to benchmark result files"
    )

    args = parser.parse_args()

    if not os.path.exists(args.groundtruth_dir):
        print(f"Error: Groundtruth directory {args.groundtruth_dir} does not exist.")
        return

    print(f"Using NPMI threshold: {args.npmi_threshold}")
    print(f"Groundtruth directory: {args.groundtruth_dir}")
    print()

    results_summary = []

    for benchmark_file in args.benchmark_files:
        if not os.path.exists(benchmark_file):
            print(f"Warning: Benchmark file {benchmark_file} not found. Skipping.")
            continue

        print(f"Processing: {benchmark_file}")
        filename, metrics_list = process_file(
            benchmark_file, args.groundtruth_dir, args.npmi_threshold
        )

        if not metrics_list:
            print(f"  Warning: No valid data found for {filename}")
            continue

        stats = calculate_statistics(metrics_list)
        stats["file"] = filename
        stats["cases_evaluated"] = len(metrics_list)
        results_summary.append(stats)

        print(f"  Cases evaluated: {len(metrics_list)}")
        print(
            f"  Median - Precision: {stats['median_precision']:.4f}, Recall: {stats['median_recall']:.4f}, F1: {stats['median_f1']:.4f}"
        )
        print(
            f"  Mean   - Precision: {stats['mean_precision']:.4f}, Recall: {stats['mean_recall']:.4f}, F1: {stats['mean_f1']:.4f}"
        )
        print()

    if not results_summary:
        print("No valid data found.")
        return

    # Print summary table
    print("=" * 100)
    print("SUMMARY TABLE")
    print("=" * 100)
    print(
        f"{'File':<40} {'Cases':<8} {'Med Prec':<10} {'Mean Prec':<10} {'Med Recall':<10} {'Mean Recall':<10} {'Med F1':<10} {'Mean F1':<10}"
    )
    print("-" * 100)

    for summary in results_summary:
        print(
            f"{summary['file']:<40} {summary['cases_evaluated']:<8} "
            f"{summary['median_precision']:<10.4f} {summary['mean_precision']:<10.4f} "
            f"{summary['median_recall']:<10.4f} {summary['mean_recall']:<10.4f} "
            f"{summary['median_f1']:<10.4f} {summary['mean_f1']:<10.4f}"
        )


if __name__ == "__main__":
    main()
