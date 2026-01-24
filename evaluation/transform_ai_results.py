import json
import re
import sys
from pathlib import Path


def load_json(path: Path, description: str, strict: bool):
    try:
        with path.open("r") as f:
            return json.load(f)
    except Exception as e:
        message = f"Error reading {description} {path}: {e}"
        if strict:
            raise RuntimeError(message) from e
        print(message)
        return {}


def transform_file(input_path, benchmark_path=None, strict_benchmark=True):
    input_path = Path(input_path)
    benchmark_path = Path(benchmark_path) if benchmark_path else None

    output_dir = input_path.parent
    basename = input_path.name

    # Extract timestamp (numbers at the end)
    match = re.search(r"(\d+_\d+)\.json$", basename)
    timestamp = match.group(1) if match else "unknown"

    output_filename = f"benchmark_{output_dir.name}_{timestamp}.json"
    output_path = output_dir / output_filename

    data = load_json(input_path, "input file", strict=True)

    benchmark_data = {}
    if benchmark_path:
        if not benchmark_path.is_file():
            message = f"Benchmark file not found: {benchmark_path}"
            if strict_benchmark:
                raise FileNotFoundError(message)
            print(message)
        else:
            benchmark_data = load_json(
                benchmark_path, "benchmark file", strict=strict_benchmark
            )

    summary = data.get("summary", {})
    ai_eval = summary.get("ai_evaluation", {})
    meta = summary.get("benchmark_metadata", {})

    cases = data.get("cases", [])
    total_cases_count = len(cases)
    successful_cases_count = sum(1 for c in cases if c.get("case_had_mappings", False))
    failed_cases_count = total_cases_count - successful_cases_count

    calculated_total_duration = 0.0
    results_list = []

    benchmark_results = {
        res.get("case_number"): res for res in benchmark_data.get("results", [])
    }

    for case in cases:
        mappings = []
        unique_s_vals = set()
        ai_case_duration = 0.0

        case_num = case.get("case_number")
        benchmark_mappings = {}
        if case_num in benchmark_results:
            bench_res = benchmark_results[case_num]
            for bench_mapping in bench_res.get("output", {}).get("mappings", []):
                key = (
                    bench_mapping.get("r_val", "").lower().strip(),
                    bench_mapping.get("s_val", "").lower().strip(),
                )
                benchmark_mappings[key] = bench_mapping.get("npmi")

        for m in case.get("mappings", []):
            s_val = m.get("chosen_s_val")
            r_val = m.get("r_val")
            if s_val:
                unique_s_vals.add(s_val)

            mapping_entry = {"r_val": r_val, "s_val": s_val}

            # Copy NPMI score from benchmark if available
            if r_val and s_val:
                key = (r_val.lower().strip(), s_val.lower().strip())
                if key in benchmark_mappings:
                    mapping_entry["npmi"] = benchmark_mappings[key]

            mappings.append(mapping_entry)
            ai_case_duration += m.get("ai_duration_seconds", 0.0) or 0.0

        case_duration = ai_case_duration
        go_service_timings = None
        python_service_timings = None

        if case_num in benchmark_results:
            bench_res = benchmark_results[case_num]
            bench_duration = bench_res.get("duration_seconds", 0.0) or 0.0
            case_duration += bench_duration
            go_service_timings = bench_res.get("go_service_timings")
            python_service_timings = bench_res.get("python_service_timings")

        calculated_total_duration += case_duration

        result_entry = {
            "case_number": case_num,
            "success": case.get("case_had_mappings", False),
            "duration_seconds": case_duration,
            "error": None,
            "output": {
                "mappings": mappings,
                "num_r": case.get("num_r_vals"),
                "num_s": len(unique_s_vals),
                "num_mappings": len(mappings),
            },
            "go_service_timings": go_service_timings,
            "python_service_timings": python_service_timings,
            "ai_timings": {"ai_total_duration_seconds": ai_case_duration},
        }
        results_list.append(result_entry)

    cases_processed = ai_eval.get("cases_processed", 0)
    avg_duration = (
        calculated_total_duration / cases_processed if cases_processed > 0 else 0
    )

    output_data = {
        "algorithm": meta.get("algorithm", "rs_jp"),
        "start_time": meta.get("benchmark_start_time"),
        "database": meta.get("database"),
        "total_cases": total_cases_count,
        "successful_cases": successful_cases_count,
        "failed_cases": failed_cases_count,
        "total_duration_seconds": calculated_total_duration,
        "average_duration_seconds": avg_duration,
        "results": results_list,
    }

    try:
        with output_path.open("w") as f:
            json.dump(output_data, f, indent=2)
        print(f"File written to {output_path}")
    except Exception as e:
        print(f"Error writing to {output_path}: {e}")


def main():
    base_dir = Path(
        "/Users/fr-son/Coding/sema-join-repos/bitmap-approach/eval-result-data"
    )
    files_to_process_raw = [
        (
            base_dir
            / "duckdb_git_tables_bench/rs_jp_ai_context/ai_evaluation_results_20260116_114506.json",
            base_dir
            / "duckdb_git_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_160123.json",
        ),
        (
            base_dir
            / "duckdb_git_tables_bench/rs_jp_ai_context/ai_evaluation_results_20260116_120519.json",
            base_dir
            / "duckdb_git_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_161458.json",
        ),
        (
            base_dir
            / "duckdb_wiki_tables_bench/rs_jp_ai_context/ai_evaluation_results_20260116_122636.json",
            base_dir
            / "duckdb_wiki_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_154426.json",
        ),
        (
            base_dir
            / "duckdb_wiki_tables_bench/rs_jp_ai_context/ai_evaluation_results_20260116_130023.json",
            base_dir
            / "duckdb_wiki_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_154521.json",
        ),
        (
            base_dir
            / "vertica_wdc_bench/rs_jp_ai_context/ai_evaluation_results_20260118_150120.json",
            base_dir
            / "vertica_wdc_bench/rs_jp_top_k_5/benchmark_rs_jp_vertica_wdc_20260118_101540.json",
        ),
        (
            base_dir
            / "vertica_wdc_bench/rs_jp_ai_context/ai_evaluation_results_20260118_234546.json",
            base_dir
            / "vertica_wdc_bench/rs_jp_top_k_5/benchmark_rs_jp_vertica_wdc_20260118_110555.json",
        ),
        (
            base_dir
            / "vertica_wdc_bench/rs_jp_ai_naive/ai_evaluation_results_20260118_140135.json",
            base_dir
            / "vertica_wdc_bench/rs_jp_top_k_5/benchmark_rs_jp_vertica_wdc_20260118_101540.json",
        ),
        (
            base_dir
            / "vertica_wdc_bench/rs_jp_ai_naive/ai_evaluation_results_20260118_224445.json",
            base_dir
            / "vertica_wdc_bench/rs_jp_top_k_5/benchmark_rs_jp_vertica_wdc_20260118_110555.json",
        ),
    ]

    # If arguments are provided, assume they are pairs of paths
    if len(sys.argv) > 1:
        args = sys.argv[1:]
        files_to_process_raw = []
        for i in range(0, len(args), 2):
            input_path = Path(args[i])
            benchmark_path = Path(args[i + 1]) if i + 1 < len(args) else None
            files_to_process_raw.append((input_path, benchmark_path))

    for input_path, benchmark_path in files_to_process_raw:
        if not input_path.exists():
            print(f"File not found: {input_path}")
            continue
        print(f"Processing {input_path} with benchmark {benchmark_path}...")
        transform_file(input_path, benchmark_path, strict_benchmark=True)


if __name__ == "__main__":
    main()
