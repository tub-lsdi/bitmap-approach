#!/usr/bin/env python3
"""Benchmark runner for CS-JP-LP algorithm"""

import argparse
import json
import csv
import os
import time
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from statistics import median

import requests

from cs_jp_lp import CSJPLPAlgorithm
from loguru import logger


class TimeoutException(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutException("Execution timed out")


def parse_case_input(case_file: Path) -> Tuple[List[str], List[str]]:
    """Parse input file: list_r, empty line, list_s"""
    with open(case_file, "r") as f:
        lines = [line.strip() for line in f.readlines()]

    # Find the empty line that separates list_r and list_s
    separator_idx = None
    for i, line in enumerate(lines):
        if line == "":
            separator_idx = i
            break

    if separator_idx is None:
        raise ValueError(f"No separator found in {case_file}")

    list_r = [line for line in lines[:separator_idx] if line]
    list_s = [line for line in lines[separator_idx + 1 :] if line]

    return list_r, list_s


def call_go_service_placeholder(
    list_r: List[str],
    list_s: List[str],
    service_url: Optional[str] = None,
) -> Dict[Tuple[str, str, str, str], float]:
    """Call Go service to get PMI scores for quads"""
    if service_url is None:
        logger.error("Service URL is required but not provided")
        return {}

    endpoint = f"{service_url}/calculate-quad-scores"
    payload = {"listR": list_r, "listS": list_s}

    try:
        logger.info(
            f"Calling Go service: list_r={len(list_r)} items, list_s={len(list_s)} items"
        )
        response = requests.post(endpoint, json=payload, timeout=300)
        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        # Convert response format to expected return type
        # Response: [{"quad": "r_i,s_j,r_k,s_l", "pmi": 2.5}, ...]
        # Expected: {(r_i, s_j, r_k, s_l): 2.5, ...}
        pmi_scores = {}
        for item in results:
            quad_str = item.get("quad", "")
            pmi = item.get("pmi", 0.0)

            # Parse quad string "r_i,s_j,r_k,s_l" into tuple
            parts = quad_str.split(",")
            if len(parts) == 4:
                quad_tuple = (parts[0], parts[1], parts[2], parts[3])
                pmi_scores[quad_tuple] = float(pmi)
            else:
                logger.warning(f"Invalid quad format: {quad_str}")

        logger.info(f"Received {len(pmi_scores)} PMI scores from Go service")
        return pmi_scores

    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling Go service: {e}")
        return {}
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"Error parsing Go service response: {e}")
        return {}


def run_single_case(
    case_num: int,
    benchmark_dir: Path,
    timeout_seconds: int,
    service_url: Optional[str] = None,
) -> Dict:
    """Run benchmark for a single case"""
    case_file = benchmark_dir / f"Case{case_num}_input.txt"

    if not case_file.exists():
        return {
            "case_number": case_num,
            "success": False,
            "duration_seconds": 0.0,
            "timeout": False,
            "error": f"Case file not found: {case_file}",
            "start_time": None,
            "end_time": None,
            "output": None,
        }

    start_time = datetime.now()
    result = {
        "case_number": case_num,
        "success": False,
        "duration_seconds": 0.0,
        "timeout": False,
        "error": None,
        "start_time": start_time.isoformat(),
        "end_time": None,
        "output": None,
    }

    # Set up timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_seconds)

    try:
        # Parse input
        list_r, list_s = parse_case_input(case_file)
        logger.info(
            f"Case {case_num}: list_r={len(list_r)} items, list_s={len(list_s)} items"
        )

        # Normalize lists to lowercase (to match Go service normalization)
        list_r_normalized = [s.lower().strip() for s in list_r]
        list_s_normalized = [s.lower().strip() for s in list_s]

        # Call Go service to get PMI scores (with normalized lists)
        w_ijkl_scores = call_go_service_placeholder(
            list_r_normalized, list_s_normalized, service_url
        )

        # Run CS-JP-LP algorithm (with normalized lists to match PMI scores)
        algorithm = CSJPLPAlgorithm()
        mappings = algorithm.create_bridge(
            list_r_normalized, list_s_normalized, w_ijkl_scores
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        result.update(
            {
                "success": True,
                "duration_seconds": duration,
                "end_time": end_time.isoformat(),
                "output": {
                    "mappings": mappings,
                    "num_r": len(list_r),
                    "num_s": len(list_s),
                    "num_mappings": len(mappings),
                },
            }
        )

    except TimeoutException:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        result.update(
            {
                "timeout": True,
                "duration_seconds": duration,
                "end_time": end_time.isoformat(),
                "error": f"Timeout after {timeout_seconds} seconds",
            }
        )

    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        result.update(
            {
                "duration_seconds": duration,
                "end_time": end_time.isoformat(),
                "error": str(e),
            }
        )
        logger.exception(f"Error in case {case_num}")

    finally:
        # Cancel the alarm
        signal.alarm(0)

    return result


def calculate_statistics(results: List[Dict]) -> Tuple[float, float]:
    """Calculate avg/median duration for successful cases"""
    successful_durations = [
        r["duration_seconds"] for r in results if r["success"] and not r["timeout"]
    ]

    if not successful_durations:
        return 0.0, 0.0

    avg_duration = sum(successful_durations) / len(successful_durations)
    med_duration = median(successful_durations)

    return avg_duration, med_duration


def save_results_json(benchmark_run: Dict, output_file: Path):
    with open(output_file, "w") as f:
        json.dump(benchmark_run, f, indent=2)


def save_results_csv(benchmark_run: Dict, output_file: Path):
    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)

        # Write header
        writer.writerow(
            [
                "case_number",
                "success",
                "duration_seconds",
                "timeout",
                "error",
                "start_time",
                "end_time",
            ]
        )

        # Write results
        for result in benchmark_run["results"]:
            writer.writerow(
                [
                    result["case_number"],
                    result["success"],
                    f"{result['duration_seconds']:.6f}",
                    result["timeout"],
                    result.get("error", ""),
                    result.get("start_time", ""),
                    result.get("end_time", ""),
                ]
            )

        # Write summary
        writer.writerow([])
        writer.writerow(["SUMMARY"])
        writer.writerow(["start_time", benchmark_run["start_time"]])
        writer.writerow(["end_time", benchmark_run["end_time"]])
        writer.writerow(
            ["total_duration_seconds", f"{benchmark_run['total_duration_seconds']:.6f}"]
        )
        writer.writerow(["max_timeout_seconds", benchmark_run["max_timeout_seconds"]])
        writer.writerow(["database", benchmark_run["database"]])
        writer.writerow(["total_cases", benchmark_run["total_cases"]])
        writer.writerow(["successful_cases", benchmark_run["successful_cases"]])
        writer.writerow(["timeout_cases", benchmark_run["timeout_cases"]])
        writer.writerow(["failed_cases", benchmark_run["failed_cases"]])

        if benchmark_run["successful_cases"] > 0:
            writer.writerow([])
            writer.writerow(["STATISTICS"])
            writer.writerow(
                [
                    "average_duration_seconds",
                    f"{benchmark_run['average_duration_seconds']:.6f}",
                ]
            )
            writer.writerow(
                [
                    "median_duration_seconds",
                    f"{benchmark_run['median_duration_seconds']:.6f}",
                ]
            )


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark CS-JP-LP algorithm with semantic join test cases"
    )
    parser.add_argument(
        "-c", "--case", type=int, help="Single case number to run (e.g., 1 for Case1)"
    )
    parser.add_argument(
        "--start", type=int, default=1, help="Starting case number (default: 1)"
    )
    parser.add_argument(
        "--end", type=int, default=50, help="Ending case number (default: 50)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Maximum execution time per case in seconds (default: 60)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=Path("data/bench_data"),
        help="Directory containing benchmark cases",
    )

    args = parser.parse_args()

    service_url = os.getenv("SERVICE_URL")
    if not service_url:
        logger.error("SERVICE_URL environment variable is required")
        sys.exit(1)

    # Determine which cases to run
    if args.case:
        case_numbers = [args.case]
    else:
        case_numbers = list(range(args.start, args.end + 1))

    # Start benchmark
    start_time = datetime.now()
    benchmark_run = {
        "start_time": start_time.isoformat(),
        "end_time": None,
        "total_duration_seconds": 0.0,
        "max_timeout_seconds": args.timeout,
        "database": "vertica",
        "total_cases": len(case_numbers),
        "successful_cases": 0,
        "timeout_cases": 0,
        "failed_cases": 0,
        "average_duration_seconds": 0.0,
        "median_duration_seconds": 0.0,
        "results": [],
    }

    logger.info(f"Starting benchmark run at {benchmark_run['start_time']}")
    logger.info(f"Database: vertica")
    logger.info(
        f"Cases: {case_numbers[0]}-{case_numbers[-1] if len(case_numbers) > 1 else case_numbers[0]}"
    )
    logger.info(f"Max timeout per case: {args.timeout} seconds")
    logger.info("=" * 80)

    # Run each case
    for case_num in case_numbers:
        logger.info(f"\nRunning Case {case_num}...")
        result = run_single_case(
            case_num, args.benchmark_dir, args.timeout, service_url
        )
        benchmark_run["results"].append(result)

        if result["success"]:
            benchmark_run["successful_cases"] += 1
            logger.info(f"  ✓ Completed in {result['duration_seconds']:.2f} seconds")
        elif result["timeout"]:
            benchmark_run["timeout_cases"] += 1
            logger.warning(
                f"  ✗ Timeout after {result['duration_seconds']:.2f} seconds"
            )
        else:
            benchmark_run["failed_cases"] += 1
            logger.error(f"  ✗ Failed: {result['error']}")

    # End benchmark
    end_time = datetime.now()
    benchmark_run["end_time"] = end_time.isoformat()
    benchmark_run["total_duration_seconds"] = (end_time - start_time).total_seconds()

    # Calculate statistics
    avg_duration, med_duration = calculate_statistics(benchmark_run["results"])
    benchmark_run["average_duration_seconds"] = avg_duration
    benchmark_run["median_duration_seconds"] = med_duration

    # Print summary
    logger.info("=" * 80)
    logger.info("\nBenchmark Summary:")
    logger.info(f"  Total cases: {benchmark_run['total_cases']}")
    logger.info(f"  Successful: {benchmark_run['successful_cases']}")
    logger.info(f"  Timeouts: {benchmark_run['timeout_cases']}")
    logger.info(f"  Failed: {benchmark_run['failed_cases']}")
    logger.info(
        f"  Total duration: {benchmark_run['total_duration_seconds']:.2f} seconds"
    )
    if benchmark_run["successful_cases"] > 0:
        logger.info(f"  Average duration (successful): {avg_duration:.2f} seconds")
        logger.info(f"  Median duration (successful): {med_duration:.2f} seconds")

    # Save results
    timestamp = start_time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path("/app/results")
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.format == "csv":
        output_file = output_dir / f"benchmark_vertica_{timestamp}.csv"
        save_results_csv(benchmark_run, output_file)
    else:
        output_file = output_dir / f"benchmark_vertica_{timestamp}.json"
        save_results_json(benchmark_run, output_file)

    logger.info(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()
