#!/usr/bin/env python3
"""
Compare benchmark results against ground truth.
Normalizes ground truth and compares with output bridge table.
"""

import json
import sys
from pathlib import Path
from typing import Set, Tuple, Dict, List


def normalize_string(s: str) -> str:
    """Normalize string by converting to lowercase and stripping whitespace."""
    return s.strip().lower()


def parse_ground_truth(ground_truth_path: Path) -> Set[Tuple[str, str]]:
    """
    Parse ground truth file.
    Format can be either:
    1. "r1\ts1\nr2\ts2\n..." (newline-separated pairs)
    2. "r1\ts1\nr2" (mixed format with tabs and newlines)

    In all cases: left value (before tab) is r_val, right value (after tab) is s_val.
    Returns a set of normalized (r_val, s_val) tuples.
    """
    ground_truth_pairs = set()

    with open(ground_truth_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by tabs to get pairs
    # Format: "r1\ts1\nr2\ts2\n..." splits into ["r1", "s1\nr2", "s2\n..."]
    parts = content.split('\t')

    if len(parts) < 2:
        return ground_truth_pairs

    # Process pairs
    current_r = parts[0].strip()

    for i in range(1, len(parts)):
        s_and_next = parts[i]

        # Split by newline to separate s_val from next r_val
        lines = s_and_next.split('\n', 1)

        s_val = lines[0].strip()

        # Add current pair if both values exist
        if current_r and s_val:
            r_val_norm = normalize_string(current_r)
            s_val_norm = normalize_string(s_val)

            if r_val_norm and s_val_norm:
                ground_truth_pairs.add((r_val_norm, s_val_norm))

        # Get next r_val if it exists
        if len(lines) > 1:
            current_r = lines[1].strip()
        else:
            break

    return ground_truth_pairs


def parse_benchmark_results(benchmark_path: Path, case_number: int) -> Set[Tuple[str, str]]:
    """
    Parse benchmark JSON file and extract mappings for a specific case.
    Returns a set of normalized (r_val, s_val) tuples.
    """
    result_pairs = set()

    with open(benchmark_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Find the case in results
    for result in data.get('results', []):
        if result.get('case_number') == case_number:
            mappings = result.get('output', {}).get('mappings', [])

            for mapping in mappings:
                r_val = normalize_string(mapping.get('r_val', ''))
                s_val = normalize_string(mapping.get('s_val', ''))

                if r_val and s_val:
                    result_pairs.add((r_val, s_val))

            break

    return result_pairs


def compare_results(
    ground_truth: Set[Tuple[str, str]],
    results: Set[Tuple[str, str]]
) -> Dict[str, any]:
    """
    Compare ground truth against results.
    Returns metrics including precision, recall, F1, and differences.
    """
    true_positives = ground_truth.intersection(results)
    false_positives = results - ground_truth
    false_negatives = ground_truth - results

    tp_count = len(true_positives)
    fp_count = len(false_positives)
    fn_count = len(false_negatives)

    precision = tp_count / (tp_count + fp_count) if (tp_count + fp_count) > 0 else 0.0
    recall = tp_count / (tp_count + fn_count) if (tp_count + fn_count) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        'ground_truth_size': len(ground_truth),
        'results_size': len(results),
        'true_positives': tp_count,
        'false_positives': fp_count,
        'false_negatives': fn_count,
        'precision': precision,
        'recall': recall,
        'f1_score': f1,
        'correct_matches': sorted(list(true_positives)),
        'incorrect_matches': sorted(list(false_positives)),
        'missing_matches': sorted(list(false_negatives))
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python compare_results.py <benchmark_json_path> [ground_truth_dir]")
        print("Example: python compare_results.py benchmark_vertica.json")
        sys.exit(1)

    benchmark_path = Path(sys.argv[1])

    # Default ground truth directory
    ground_truth_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent.parent / 'benchmark-data'

    # Validate benchmark file exists
    if not benchmark_path.exists():
        print(f"Error: Benchmark file not found: {benchmark_path}")
        sys.exit(1)

    # Load benchmark data
    with open(benchmark_path, 'r', encoding='utf-8') as f:
        benchmark_data = json.load(f)

    # Extract all case numbers from results
    results_list = benchmark_data.get('results', [])
    case_numbers = [result.get('case_number') for result in results_list if result.get('case_number')]

    print(f"Found {len(case_numbers)} cases in benchmark file: {sorted(case_numbers)}")
    print(f"Ground truth directory: {ground_truth_dir}")
    print("="*80)

    # Store all comparisons
    all_comparisons = {}
    summary_stats = {
        'total_cases': 0,
        'successful_comparisons': 0,
        'failed_comparisons': 0,
        'missing_ground_truth': [],
        'total_precision': 0.0,
        'total_recall': 0.0,
        'total_f1': 0.0
    }

    # Process each case
    for case_number in sorted(case_numbers):
        ground_truth_file = ground_truth_dir / f"Case{case_number}_groundtruth.txt"

        print(f"\n{'='*80}")
        print(f"CASE {case_number}")
        print('='*80)

        # Check if ground truth exists
        if not ground_truth_file.exists():
            print(f"WARNING: Ground truth file not found: {ground_truth_file}")
            summary_stats['missing_ground_truth'].append(case_number)
            summary_stats['failed_comparisons'] += 1
            continue

        try:
            # Parse ground truth
            print(f"Parsing ground truth from: {ground_truth_file.name}")
            ground_truth = parse_ground_truth(ground_truth_file)
            print(f"Found {len(ground_truth)} ground truth pairs")

            # Parse results
            results = parse_benchmark_results(benchmark_path, case_number)
            print(f"Found {len(results)} result pairs")

            # Compare
            comparison = compare_results(ground_truth, results)
            comparison['case_number'] = case_number
            all_comparisons[case_number] = comparison

            # Display results
            print(f"\nMetrics:")
            print(f"  Ground Truth Size: {comparison['ground_truth_size']}")
            print(f"  Results Size: {comparison['results_size']}")
            print(f"  True Positives: {comparison['true_positives']}")
            print(f"  False Positives: {comparison['false_positives']}")
            print(f"  False Negatives: {comparison['false_negatives']}")
            print(f"  Precision: {comparison['precision']:.4f}")
            print(f"  Recall: {comparison['recall']:.4f}")
            print(f"  F1 Score: {comparison['f1_score']:.4f}")

            # Update summary stats
            summary_stats['total_cases'] += 1
            summary_stats['successful_comparisons'] += 1
            summary_stats['total_precision'] += comparison['precision']
            summary_stats['total_recall'] += comparison['recall']
            summary_stats['total_f1'] += comparison['f1_score']

            # Show differences if any
            if comparison['incorrect_matches']:
                print(f"\n  Incorrect Matches ({len(comparison['incorrect_matches'])}):")
                for r_val, s_val in comparison['incorrect_matches'][:5]:  # Show first 5
                    print(f"    {r_val} -> {s_val}")
                if len(comparison['incorrect_matches']) > 5:
                    print(f"    ... and {len(comparison['incorrect_matches']) - 5} more")

            if comparison['missing_matches']:
                print(f"\n  Missing Matches ({len(comparison['missing_matches'])}):")
                for r_val, s_val in comparison['missing_matches'][:5]:  # Show first 5
                    print(f"    {r_val} -> {s_val}")
                if len(comparison['missing_matches']) > 5:
                    print(f"    ... and {len(comparison['missing_matches']) - 5} more")

        except Exception as e:
            print(f"ERROR processing case {case_number}: {e}")
            summary_stats['failed_comparisons'] += 1
            continue

    # Print summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total Cases Processed: {summary_stats['total_cases']}")
    print(f"Successful Comparisons: {summary_stats['successful_comparisons']}")
    print(f"Failed Comparisons: {summary_stats['failed_comparisons']}")

    if summary_stats['missing_ground_truth']:
        print(f"Missing Ground Truth Files: {summary_stats['missing_ground_truth']}")

    if summary_stats['successful_comparisons'] > 0:
        avg_precision = summary_stats['total_precision'] / summary_stats['successful_comparisons']
        avg_recall = summary_stats['total_recall'] / summary_stats['successful_comparisons']
        avg_f1 = summary_stats['total_f1'] / summary_stats['successful_comparisons']

        print(f"\nAverage Metrics:")
        print(f"  Average Precision: {avg_precision:.4f}")
        print(f"  Average Recall: {avg_recall:.4f}")
        print(f"  Average F1 Score: {avg_f1:.4f}")

    # Save detailed results to JSON
    output_file = benchmark_path.parent / f"comparison_all_cases_{benchmark_path.stem}.json"
    output_data = {
        'benchmark_file': str(benchmark_path),
        'ground_truth_dir': str(ground_truth_dir),
        'summary': summary_stats,
        'cases': all_comparisons
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()
