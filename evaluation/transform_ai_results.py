import json
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def transform_file(input_path, benchmark_path=None):
    output_dir = os.path.dirname(input_path)
    basename = os.path.basename(input_path)

    # Extract timestamp (numbers at the end)
    match = re.search(r'(\d+_\d+)\.json$', basename)
    if match:
        timestamp = match.group(1)
    else:
        timestamp = 'unknown'

    output_filename = f'benchmark_rs_jp_ai_{timestamp}.json'
    output_path = os.path.join(output_dir, output_filename)

    try:
        with open(input_path, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {input_path}: {e}")
        return

    benchmark_data = {}
    if benchmark_path:
        try:
            with open(benchmark_path, 'r') as f:
                benchmark_data = json.load(f)
        except Exception as e:
            print(f"Error reading benchmark file {benchmark_path}: {e}")

    summary = data.get('summary', {})
    ai_eval = summary.get('ai_evaluation', {})
    meta = summary.get('benchmark_metadata', {})

    cases = data.get('cases', [])
    total_cases_count = len(cases)
    successful_cases_count = sum(1 for c in cases if c.get('case_had_mappings', False))
    failed_cases_count = total_cases_count - successful_cases_count

    calculated_total_duration = 0
    results_list = []

    benchmark_results = {res.get('case_number'): res for res in benchmark_data.get('results', [])}

    for case in cases:
        mappings = []
        unique_s_vals = set()
        ai_case_duration = 0.0
        
        for m in case.get('mappings', []):
            s_val = m.get('chosen_s_val')
            if s_val:
                unique_s_vals.add(s_val)
            mappings.append({
                "r_val": m.get('r_val'),
                "s_val": s_val
            })
            ai_case_duration += m.get('ai_duration_seconds', 0)

        case_duration = ai_case_duration
        go_service_timings = None
        python_service_timings = None
        
        # Add duration from benchmark file if available
        case_num = case.get('case_number')
        if case_num in benchmark_results:
            bench_res = benchmark_results[case_num]
            bench_duration = bench_res.get('duration_seconds', 0)
            case_duration += bench_duration
            go_service_timings = bench_res.get("go_service_timings")
            python_service_timings = bench_res.get("python_service_timings")

        calculated_total_duration += case_duration

        result_entry = {
            "case_number": case.get('case_number'),
            "success": case.get('case_had_mappings', False),
            "duration_seconds": case_duration,
            "error": None,
            "output": {
                "mappings": mappings,
                "num_r": case.get('num_r_vals'),
                "num_s": len(unique_s_vals),
                "num_mappings": len(mappings)
            },
            "go_service_timings": go_service_timings,
            "python_service_timings": python_service_timings,
            "ai_timings": {
                "ai_total_duration_seconds": ai_case_duration
            }
        }
        results_list.append(result_entry)

    cases_processed = ai_eval.get("cases_processed", 0)
    avg_duration = calculated_total_duration / cases_processed if cases_processed > 0 else 0

    output_data = {
        "algorithm": meta.get('algorithm', 'rs_jp'),
        "start_time": meta.get('benchmark_start_time'),
        "database": meta.get('database'),
        "total_cases": total_cases_count,
        "successful_cases": successful_cases_count,
        "failed_cases": failed_cases_count,
        "total_duration_seconds": calculated_total_duration,
        "average_duration_seconds": avg_duration,
        "results": results_list
    }

    try:
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"File written to {output_path}")
    except Exception as e:
        print(f"Error writing to {output_path}: {e}")

def main():
    # List of files to process
    base_dir = '/Users/fr-son/Coding/sema-join-repos/bitmap-approach/eval-result-data/'
    files_to_process = [
        (f'{base_dir}/duckdb_git_tables_bench/rs_jp_ai/ai_evaluation_results_20260114_022835.json', f'{base_dir}/duckdb_git_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_155003.json'),
        (f'{base_dir}/duckdb_git_tables_bench/rs_jp_ai/ai_evaluation_results_20260114_053809.json', f'{base_dir}/duckdb_git_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_160123.json'),
        (f'{base_dir}/duckdb_git_tables_bench/rs_jp_ai/ai_evaluation_results_20260114_051837.json', f'{base_dir}/duckdb_git_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_161458.json'),
        (f'{base_dir}/duckdb_wiki_tables_bench/rs_jp_ai/ai_evaluation_results_20260114_014411.json', f'{base_dir}/duckdb_wiki_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_154339.json'),
        (f'{base_dir}/duckdb_wiki_tables_bench/rs_jp_ai/ai_evaluation_results_20260114_025120.json', f'{base_dir}/duckdb_wiki_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_154426.json'),
        (f'{base_dir}/duckdb_wiki_tables_bench/rs_jp_ai/ai_evaluation_results_20260114_044641.json', f'{base_dir}/duckdb_wiki_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_154521.json'),

        (f'{base_dir}/duckdb_wiki_tables_bench/rs_jp_ai_context/ai_evaluation_results_20260114_132612.json', f'{base_dir}/duckdb_wiki_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_154339.json'),
        (f'{base_dir}/duckdb_git_tables_bench/rs_jp_ai_context/ai_evaluation_results_20260116_095127.json', f'{base_dir}/duckdb_git_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_155003.json'),
    ]

    # If arguments are provided, assume they are pairs of paths
    if len(sys.argv) > 1:
        args = sys.argv[1:]
        files_to_process = []
        # Process arguments in pairs
        for i in range(0, len(args), 2):
            input_path = args[i]
            benchmark_path = args[i+1] if i+1 < len(args) else None
            files_to_process.append((input_path, benchmark_path))

    for input_path, benchmark_path in files_to_process:
        if os.path.exists(input_path):
            print(f"Processing {input_path} with benchmark {benchmark_path}...")
            transform_file(input_path, benchmark_path)
        else:
            print(f"File not found: {input_path}")

if __name__ == "__main__":
    main()
