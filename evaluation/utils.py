import json
import sys
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
