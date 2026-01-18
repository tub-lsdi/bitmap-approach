import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from statistics import median
from zoneinfo import ZoneInfo

import requests

from rs_jp import RSJPAlgorithm
from loguru import logger


def parse_case_input(case_file: Path) -> Tuple[List[str], List[str]]:
    """Parse input file: list_r, empty line, list_s"""
    with open(case_file, "r") as f:
        lines = [line.strip() for line in f.readlines()]

    separator_idx = None
    for i, line in enumerate(lines):
        if line == "":
            separator_idx = i
            break

    if separator_idx is None:
        raise ValueError(f"No separator found in {case_file}")

    list_r = [line for line in lines[:separator_idx] if line]
    list_s = [line for line in lines[separator_idx + 1:] if line]

    return list_r, list_s


def call_go_service_row_pmis(
    list_r: List[str],
    list_s: List[str],
    service_url: Optional[str] = None,
) -> Tuple[Dict[Tuple[str, str], float], List[Dict]]:
    """Call Go service /row-pmis endpoint to get row-level NPMI scores"""
    if service_url is None:
        logger.error("Service URL is required but not provided")
        return {}, []

    endpoint = f"{service_url}/row-pmis"
    payload = {"listR": list_r, "listS": list_s}

    try:
        logger.info(
            f"Calling Go service: list_r={len(list_r)} items, list_s={len(list_s)} items"
        )
        response = requests.post(endpoint, json=payload)
        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])
        timings = data.get("timings", [])

        # Response format: [{"r_i": "val", "s_j": "val", "pmi": 0.85}, ...]
        # Convert to: {(r_i, s_j): 0.85, ...}
        pmi_scores = {}
        for item in results:
            r_val = item.get("r_i", "")
            s_val = item.get("s_j", "")
            pmi = item.get("pmi", 0.0)

            if r_val and s_val:
                pmi_scores[(r_val, s_val)] = float(pmi)
                # Validate NPMI range
                if pmi < -1.0 or pmi > 1.0:
                    logger.warning(
                        f"NPMI value out of range [-1, 1]: {pmi} for ({r_val}, {s_val})")

        logger.info(f"Received {len(pmi_scores)} PMI scores from Go service")
        return pmi_scores, timings

    except requests.exceptions.RequestException as e:
        logger.error(f"Error calling Go service: {e}")
        return {}, []
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error(f"Error parsing Go service response: {e}")
        return {}, []


def run_single_case(
    case_num: int,
    benchmark_dir: Path,
    service_url: Optional[str] = None,
) -> Dict:
    """Run benchmark for a single case"""
    case_file = benchmark_dir / f"Case{case_num}_input.txt"

    if not case_file.exists():
        return {
            "case_number": case_num,
            "success": False,
            "duration_seconds": 0.0,
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
        "error": None,
        "start_time": start_time.isoformat(),
        "end_time": None,
        "output": None,
    }

    try:
        list_r, list_s = parse_case_input(case_file)
        logger.info(
            f"Case {case_num}: list_r={len(list_r)} items, list_s={len(list_s)} items"
        )

        # Normalize to match Go service normalization
        list_r_normalized = [s.lower().strip() for s in list_r]
        list_s_normalized = [s.lower().strip() for s in list_s]

        pmi_scores, go_service_timings = call_go_service_row_pmis(
            list_r_normalized, list_s_normalized, service_url
        )

        algorithm = RSJPAlgorithm()
        bridge_table, python_timings = algorithm.create_bridge(
            list_r_normalized, list_s_normalized, pmi_scores, top_k=5
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        go_service_timings_dict = {}
        for timing in go_service_timings:
            step_name = timing.get("step", "unknown")
            go_service_timings_dict[step_name] = {
                "start_time": timing.get("start_time"),
                "end_time": timing.get("end_time"),
                "duration_seconds": timing.get("duration_seconds", 0.0),
            }

        result.update(
            {
                "success": True,
                "duration_seconds": duration,
                "end_time": end_time.isoformat(),
                "go_service_timings": go_service_timings_dict,
                "python_service_timings": python_timings,
                "output": {
                    "mappings": bridge_table,
                    "num_r": len(list_r),
                    "num_s": len(list_s),
                    "num_mappings": len(bridge_table),
                },
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

    return result


def calculate_statistics(results: List[Dict]) -> Tuple[float, float]:
    """Calculate avg/median duration for successful cases"""
    successful_durations = [r["duration_seconds"]
                            for r in results if r["success"]]

    if not successful_durations:
        return 0.0, 0.0

    avg_duration = sum(successful_durations) / len(successful_durations)
    med_duration = median(successful_durations)

    return avg_duration, med_duration


def save_results_json(benchmark_run: Dict, output_file: Path):
    with open(output_file, "w") as f:
        json.dump(benchmark_run, f, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark RS-JP algorithm with semantic join test cases"
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

    if args.case:
        case_numbers = [args.case] if args.case != 13 else []
        if args.case == 13:
            logger.warning("Case 13 is skipped (excluded from benchmarks)")
    else:
        case_numbers = [n for n in range(args.start, args.end + 1) if n != 13]
        if args.start <= 13 <= args.end:
            logger.warning("Case 13 is skipped (excluded from benchmarks)")

    berlin_tz = ZoneInfo("Europe/Berlin")
    start_time_utc = datetime.now(timezone.utc)
    start_time_berlin = start_time_utc.astimezone(berlin_tz)
    start_time = datetime.now()

    benchmark_run = {
        "algorithm": "rs_jp",
        "start_time": start_time.isoformat(),
        "start_time_berlin": start_time_berlin.isoformat(),
        "end_time": None,
        "total_duration_seconds": 0.0,
        "database": "vertica",
        "total_cases": len(case_numbers),
        "successful_cases": 0,
        "failed_cases": 0,
        "average_duration_seconds": 0.0,
        "median_duration_seconds": 0.0,
        "results": [],
    }

    logger.info(
        f"Starting RS-JP benchmark run at {benchmark_run['start_time']}")
    logger.info(f"Algorithm: rs_jp")
    logger.info(f"Database: vertica")
    logger.info(
        f"Cases: {case_numbers[0]}-{case_numbers[-1] if len(case_numbers) > 1 else case_numbers[0]}"
    )
    logger.info("=" * 80)

    timestamp_berlin = start_time_berlin.strftime("%Y%m%d_%H%M%S")
    output_dir = Path("/app/results")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / \
        f"benchmark_rs_jp_vertica_{timestamp_berlin}.json"

    for case_num in case_numbers:
        logger.info(f"\nRunning Case {case_num}...")
        result = run_single_case(case_num, args.benchmark_dir, service_url)
        benchmark_run["results"].append(result)

        if result["success"]:
            benchmark_run["successful_cases"] += 1
            logger.info(
                f"  ✓ Completed in {result['duration_seconds']:.2f} seconds")
        else:
            benchmark_run["failed_cases"] += 1
            logger.error(f"  ✗ Failed: {result['error']}")

        current_time = datetime.now()
        benchmark_run["end_time"] = current_time.isoformat()
        benchmark_run["total_duration_seconds"] = (
            current_time - start_time
        ).total_seconds()

        avg_duration, med_duration = calculate_statistics(
            benchmark_run["results"])
        benchmark_run["average_duration_seconds"] = avg_duration
        benchmark_run["median_duration_seconds"] = med_duration

        save_results_json(benchmark_run, output_file)
        logger.info(f"  Results saved to: {output_file}")

    end_time = datetime.now()
    benchmark_run["end_time"] = end_time.isoformat()
    benchmark_run["total_duration_seconds"] = (
        end_time - start_time).total_seconds()

    avg_duration, med_duration = calculate_statistics(benchmark_run["results"])
    benchmark_run["average_duration_seconds"] = avg_duration
    benchmark_run["median_duration_seconds"] = med_duration

    save_results_json(benchmark_run, output_file)

    logger.info("=" * 80)
    logger.info("\nBenchmark Summary:")
    logger.info(f"  Algorithm: rs_jp")
    logger.info(f"  Total cases: {benchmark_run['total_cases']}")
    logger.info(f"  Successful: {benchmark_run['successful_cases']}")
    logger.info(f"  Failed: {benchmark_run['failed_cases']}")
    logger.info(
        f"  Total duration: {benchmark_run['total_duration_seconds']:.2f} seconds"
    )
    if benchmark_run["successful_cases"] > 0:
        logger.info(
            f"  Average duration (successful): {avg_duration:.2f} seconds")
        logger.info(
            f"  Median duration (successful): {med_duration:.2f} seconds")

    logger.info(f"\nFinal results saved to: {output_file}")


if __name__ == "__main__":
    main()
