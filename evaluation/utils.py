import json
import sys
import os
import re
from typing import Set, Tuple, List, Dict


def load_groundtruth(filepath: str) -> Set[Tuple[str, str]]:
    mappings = set()
    try:
        with open(filepath, 'r') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    mappings.add((parts[0].lower().strip(), parts[1].lower().strip()))
    except FileNotFoundError:
        print(f"Error: Groundtruth file {filepath} not found.", file=sys.stderr)
    return mappings


def load_results(filepath: str) -> List[Dict]:
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        return data.get('results', [])
    except FileNotFoundError:
        print(f"Error: Result file {filepath} not found.", file=sys.stderr)
        return []
    except json.JSONDecodeError:
        print(f"Error: Failed to decode JSON from {filepath}.", file=sys.stderr)
        return []


def calculate_case_metrics(groundtruth: Set[Tuple[str, str]], results: List[Dict]) -> Dict:
    result_mappings = set()
    for m in results:
        if 'r_val' in m and 's_val' in m:
             result_mappings.add((m['r_val'].lower().strip(), m['s_val'].lower().strip()))

    tp = len(groundtruth.intersection(result_mappings))
    fp = len(result_mappings - groundtruth)
    fn = len(groundtruth - result_mappings)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn
    }


def extract_case_timings(case: Dict) -> Dict:
    """
    Extracts duration_seconds from go_service_timings and python_service_timings.
    Returns a dictionary with the same structure containing only the duration values.
    """
    timings = {
        "go_service_timings": {},
        "python_service_timings": {}
    }

    for service in ["go_service_timings", "python_service_timings"]:
        service_data = case.get(service, {})
        for step, data in service_data.items():
            if isinstance(data, dict):
                timings[service][step] = data.get("duration_seconds")
            else:
                # Handle cases where it might already be a float
                timings[service][step] = data

    return timings


def get_short_filename(filepath: str) -> str:
    """
    Shortens a benchmark filename by removing the 'benchmark_' prefix,
    the extension, and the trailing timestamp.
    """
    filename = os.path.basename(filepath)
    if filename.startswith("benchmark_"):
        filename = filename[len("benchmark_"):]
    filename = os.path.splitext(filename)[0]
    filename = re.sub(r'_\d{8}_\d{6}$', '', filename)
    return filename
