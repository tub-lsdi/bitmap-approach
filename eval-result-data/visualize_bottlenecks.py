#!/usr/bin/env python3
"""
Visualize detailed timing breakdown showing bottlenecks.
Shows where time is spent in Go service (DuckDB operations) and Python service.
"""

import json
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


def load_benchmark_data(json_path):
    """Load benchmark data from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def extract_detailed_timings(benchmark_data):
    """Extract detailed timing breakdown for each case."""
    case_timings = []

    for result in benchmark_data.get('results', []):
        if not result.get('success', False):
            continue

        case_num = result['case_number']

        # Extract Go service timings
        go_timings = result.get('go_service_timings', {})
        duckdb_connection = go_timings.get(
            'duckdb_connection', {}).get('duration_seconds', 0)
        load_bitmaps = go_timings.get(
            'load_and_create_bitmaps', {}).get('duration_seconds', 0)
        filter_bitmaps = go_timings.get(
            'filter_bitmaps_to_relevant_tables', {}).get('duration_seconds', 0)
        pair_counts = go_timings.get(
            'calculate_pair_table_counts', {}).get('duration_seconds', 0)
        quad_scores = go_timings.get(
            'calculate_quad_scores', {}).get('duration_seconds', 0)
        total_count = go_timings.get(
            'get_total_table_count', {}).get('duration_seconds', 0)
        pmi_scores = go_timings.get(
            'calculate_pmi_scores', {}).get('duration_seconds', 0)

        # Extract Python service timings
        py_timings = result.get('python_service_timings', {})
        solve_cilp = py_timings.get('step1_solve_cilp', 0)
        extract_join = py_timings.get('step2_extract_join', 0)
        convert_output = py_timings.get('step3_convert_output', 0)

        # Total duration
        total_duration = result['duration_seconds']

        # Calculate "other" time (overhead, network, etc.)
        accounted_time = (duckdb_connection + load_bitmaps + filter_bitmaps +
                          pair_counts + quad_scores + total_count + pmi_scores +
                          solve_cilp + extract_join + convert_output)
        other_time = max(0, total_duration - accounted_time)

        case_timings.append({
            'case': case_num,
            'duckdb_connection': duckdb_connection,
            'load_bitmaps': load_bitmaps,
            'filter_bitmaps': filter_bitmaps,
            'pair_counts': pair_counts,
            'quad_scores': quad_scores,
            'total_count': total_count,
            'pmi_scores': pmi_scores,
            'solve_cilp': solve_cilp,
            'extract_join': extract_join,
            'convert_output': convert_output,
            'other': other_time,
            'total': total_duration
        })

    return case_timings


def create_stacked_bar_chart(case_timings, output_path):
    """Create stacked bar chart showing time breakdown by case."""
    fig, ax = plt.subplots(figsize=(22, 10))

    cases = [ct['case'] for ct in case_timings]

    # Group operations by where they execute:
    # NOTE: load_bitmaps includes DuckDB query + network transfer + Go bitmap creation (inseparable)
    duckdb_query_load = np.array([ct['load_bitmaps'] for ct in case_timings])
    duckdb_total_count = np.array([ct['total_count'] for ct in case_timings])

    # GO SERVICE operations (pure in-memory bitmap operations)
    go_filter = np.array([ct['filter_bitmaps'] for ct in case_timings])
    go_calc = np.array([ct['pair_counts'] + ct['quad_scores'] +
                       ct['pmi_scores'] for ct in case_timings])

    # PYTHON SERVICE operations
    python_ops = np.array([ct['solve_cilp'] + ct['extract_join'] +
                          ct['convert_output'] for ct in case_timings])

    # OTHER (connection setup)
    other = np.array([ct['other'] + ct['duckdb_connection']
                     for ct in case_timings])

    x = np.arange(len(cases))
    width = 0.8

    # Create stacked bars with clear labeling
    p1 = ax.bar(x, duckdb_query_load, width,
                label='Data Loading (DuckDB query + network + bitmap creation)',
                color='#d62728', alpha=0.8)
    p2 = ax.bar(x, duckdb_total_count, width, bottom=duckdb_query_load,
                label='DuckDB: COUNT Query', color='#ff7f0e', alpha=0.8)
    p3 = ax.bar(x, go_filter, width,
                bottom=duckdb_query_load + duckdb_total_count,
                label='Go: Filter Bitmaps', color='#1f77b4', alpha=0.8)
    p4 = ax.bar(x, go_calc, width,
                bottom=duckdb_query_load + duckdb_total_count + go_filter,
                label='Go: Bitmap Calculations', color='#17becf', alpha=0.8)
    p5 = ax.bar(x, python_ops, width,
                bottom=duckdb_query_load + duckdb_total_count + go_filter + go_calc,
                label='Python: CILP Solver', color='#2ca02c', alpha=0.8)
    p6 = ax.bar(x, other, width,
                bottom=duckdb_query_load + duckdb_total_count +
                go_filter + go_calc + python_ops,
                label='Connection Overhead', color='#7f7f7f', alpha=0.8)

    ax.set_xlabel('Case Number', fontsize=13, fontweight='bold')
    ax.set_ylabel('Execution Time (seconds)', fontsize=13, fontweight='bold')
    ax.set_title('Time Breakdown by Operation - All Cases',
                 fontsize=15, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'C{c}' for c in cases],
                       rotation=45, ha='right', fontsize=9)
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def create_average_breakdown_pie(case_timings, output_path):
    """Create pie chart showing average time breakdown across all cases."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8))

    # Calculate averages
    avg_load_bitmaps = np.mean([ct['load_bitmaps'] for ct in case_timings])
    avg_total_count = np.mean([ct['total_count'] for ct in case_timings])
    avg_filter = np.mean([ct['filter_bitmaps'] for ct in case_timings])
    avg_calc = np.mean([ct['pair_counts'] + ct['quad_scores'] +
                       ct['pmi_scores'] for ct in case_timings])
    avg_python = np.mean([ct['solve_cilp'] + ct['extract_join'] +
                         ct['convert_output'] for ct in case_timings])
    avg_other = np.mean([ct['other'] + ct['duckdb_connection']
                        for ct in case_timings])

    total_avg = avg_load_bitmaps + avg_total_count + \
        avg_filter + avg_calc + avg_python + avg_other

    # Pie chart 1: Average time breakdown
    labels = [
        'Data Loading\n(DB+Network+Bitmaps)',
        'DuckDB COUNT Query',
        'Go: Filter Bitmaps',
        'Go: Calculations',
        'Python: CILP',
        'Connection'
    ]
    sizes = [avg_load_bitmaps, avg_total_count,
             avg_filter, avg_calc, avg_python, avg_other]
    colors = ['#d62728', '#ff7f0e', '#1f77b4', '#17becf', '#2ca02c', '#7f7f7f']
    explode = (0.1, 0.05, 0, 0, 0, 0)  # Explode the largest slice more

    wedges, texts, autotexts = ax1.pie(sizes, explode=explode, labels=labels, colors=colors,
                                       autopct=lambda pct: f'{pct:.1f}%\n({pct/100*total_avg:.1f}s)',
                                       shadow=True, startangle=90, textprops={'fontsize': 9})

    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')

    ax1.set_title(f'Detailed Time Breakdown\n(Total: {total_avg:.1f}s per case)',
                  fontsize=13, fontweight='bold')

    # Pie chart 2: High-level breakdown
    data_loading = avg_load_bitmaps  # This is the mixed operation
    db_queries = avg_total_count     # Pure DuckDB
    go_processing = avg_filter + avg_calc  # Pure Go
    labels2 = ['Data Loading\n(mixed: DB scan + network + Go)',
               'DuckDB Queries', 'Go Processing', 'Python', 'Other']
    sizes2 = [data_loading, db_queries, go_processing, avg_python, avg_other]
    colors2 = ['#d62728', '#ff7f0e', '#1f77b4', '#2ca02c', '#7f7f7f']
    explode2 = (0.15, 0.05, 0, 0, 0)

    wedges2, texts2, autotexts2 = ax2.pie(sizes2, explode=explode2, labels=labels2, colors=colors2,
                                          autopct=lambda pct: f'{pct:.1f}%\n({pct/100*total_avg:.1f}s)',
                                          shadow=True, startangle=90, textprops={'fontsize': 11})

    for autotext in autotexts2:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(12)

    ax2.set_title(f'High-Level Time Distribution\n(Total: {total_avg:.1f}s per case)',
                  fontsize=13, fontweight='bold')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def create_bottleneck_analysis(case_timings, output_path):
    """Create horizontal bar chart showing top bottlenecks."""
    fig, ax = plt.subplots(figsize=(14, 10))

    # Calculate total time spent in each operation across all cases
    total_load_bitmaps = sum([ct['load_bitmaps'] for ct in case_timings])
    total_total_count = sum([ct['total_count'] for ct in case_timings])
    total_filter = sum([ct['filter_bitmaps'] for ct in case_timings])
    total_pair_counts = sum([ct['pair_counts'] for ct in case_timings])
    total_quad_scores = sum([ct['quad_scores'] for ct in case_timings])
    total_pmi_scores = sum([ct['pmi_scores'] for ct in case_timings])
    total_solve_cilp = sum([ct['solve_cilp'] for ct in case_timings])
    total_extract_join = sum([ct['extract_join'] for ct in case_timings])
    total_convert_output = sum([ct['convert_output'] for ct in case_timings])
    total_other = sum([ct['other'] + ct['duckdb_connection']
                      for ct in case_timings])

    operations = [
        'Data Loading (DuckDB scan + network + Go bitmap creation)',
        'DuckDB: COUNT(DISTINCT tableid) Query',
        'Go: Filter Bitmaps',
        'Python: Solve CILP',
        'Go: Calculate Quad Scores',
        'Go: Calculate Pair Counts',
        'Python: Convert Output',
        'Go: Calculate PMI Scores',
        'Python: Extract Join',
        'Connection Overhead'
    ]

    times = [
        total_load_bitmaps,
        total_total_count,
        total_filter,
        total_solve_cilp,
        total_quad_scores,
        total_pair_counts,
        total_convert_output,
        total_pmi_scores,
        total_extract_join,
        total_other
    ]

    # Sort by time
    sorted_indices = np.argsort(times)[::-1]
    operations = [operations[i] for i in sorted_indices]
    times = [times[i] for i in sorted_indices]

    colors = ['#d62728' if 'Data Loading' in op or op.startswith('Vertica') else
              '#1f77b4' if op.startswith('Go') else
              '#2ca02c' if op.startswith('Python') else '#7f7f7f'
              for op in operations]

    y_pos = np.arange(len(operations))
    bars = ax.barh(y_pos, times, color=colors, alpha=0.8,
                   edgecolor='black', linewidth=0.5)

    # Add value labels
    for i, (bar, time) in enumerate(zip(bars, times)):
        width = bar.get_width()
        percentage = (time / sum(times)) * 100
        ax.text(width, bar.get_y() + bar.get_height()/2,
                f' {time:.1f}s ({percentage:.1f}%)',
                ha='left', va='center', fontsize=10, fontweight='bold')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(operations, fontsize=11)
    ax.set_xlabel('Total Time Across All Cases (seconds)',
                  fontsize=12, fontweight='bold')
    ax.set_title('Bottleneck Analysis: Total Time by Operation',
                 fontsize=14, fontweight='bold')
    ax.grid(axis='x', alpha=0.3, linestyle='--')

    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#d62728', alpha=0.8,
              label='Data Loading & DB Queries (mixed)'),
        Patch(facecolor='#1f77b4', alpha=0.8, label='Go Service'),
        Patch(facecolor='#2ca02c', alpha=0.8, label='Python Service'),
        Patch(facecolor='#7f7f7f', alpha=0.8, label='Connection Overhead')
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=11)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def create_duckdb_operations_detail(case_timings, output_path):
    """Create detailed breakdown of all Go service operations (DuckDB + in-memory)."""
    fig, ax = plt.subplots(figsize=(20, 8))

    cases = [ct['case'] for ct in case_timings]

    load_bitmaps = [ct['load_bitmaps'] for ct in case_timings]
    total_count = [ct['total_count'] for ct in case_timings]
    filter_bitmaps = [ct['filter_bitmaps'] for ct in case_timings]
    pair_counts = [ct['pair_counts'] for ct in case_timings]
    quad_scores = [ct['quad_scores'] for ct in case_timings]
    pmi_scores = [ct['pmi_scores'] for ct in case_timings]

    x = np.arange(len(cases))
    width = 0.15

    ax.bar(x - 2.5*width, load_bitmaps, width,
           label='Data Loading (mixed)', color='#d62728', alpha=0.8)
    ax.bar(x - 1.5*width, total_count, width,
           label='COUNT Query', color='#ff7f0e', alpha=0.8)
    ax.bar(x - 0.5*width, filter_bitmaps, width,
           label='Filter Bitmaps', color='#1f77b4', alpha=0.8)
    ax.bar(x + 0.5*width, pair_counts, width,
           label='Pair Counts', color='#17becf', alpha=0.8)
    ax.bar(x + 1.5*width, quad_scores, width,
           label='Quad Scores', color='#9edae5', alpha=0.8)
    ax.bar(x + 2.5*width, pmi_scores, width,
           label='PMI Scores', color='#aec7e8', alpha=0.8)

    ax.set_xlabel('Case Number', fontsize=12, fontweight='bold')
    ax.set_ylabel('Execution Time (seconds)', fontsize=12, fontweight='bold')
    ax.set_title('Go Service Operations Breakdown by Case',
                 fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'C{c}' for c in cases],
                       rotation=45, ha='right', fontsize=9)
    ax.legend(fontsize=10, loc='upper left')
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved: {output_path}")
    plt.close()


def main():
    import sys

    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python visualize_bottlenecks.py <benchmark_json_file>")
        print("Example: python visualize_bottlenecks.py benchmark_vertica_20251206_233016.json")
        sys.exit(1)

    # Paths
    base_dir = Path(__file__).parent
    benchmark_file = Path(sys.argv[1])

    # If relative path provided, make it relative to base_dir
    if not benchmark_file.is_absolute():
        benchmark_file = base_dir / benchmark_file

    # Load benchmark data
    print("Loading detailed timing data...")
    data = load_benchmark_data(benchmark_file)

    # Extract detailed timings
    all_timings = extract_detailed_timings(data)

    print(f"Total cases with detailed timing: {len(all_timings)}")

    # Create output directory
    output_dir = base_dir / "visualizations"
    output_dir.mkdir(exist_ok=True)

    # Create visualizations
    print("\nCreating bottleneck analysis visualizations...")

    create_stacked_bar_chart(
        all_timings,
        output_dir / "14_time_breakdown_stacked.png"
    )

    create_average_breakdown_pie(
        all_timings,
        output_dir / "15_average_time_breakdown_pie.png"
    )

    create_bottleneck_analysis(
        all_timings,
        output_dir / "16_bottleneck_analysis.png"
    )

    create_duckdb_operations_detail(
        all_timings,
        output_dir / "17_duckdb_operations_detail.png"
    )

    # Print summary
    print("\n" + "="*80)
    print("BOTTLENECK ANALYSIS")
    print("="*80)

    avg_load = np.mean([ct['load_bitmaps'] for ct in all_timings])
    avg_total_count = np.mean([ct['total_count'] for ct in all_timings])
    avg_filter = np.mean([ct['filter_bitmaps'] for ct in all_timings])
    avg_calc = np.mean([ct['pair_counts'] + ct['quad_scores'] +
                       ct['pmi_scores'] for ct in all_timings])
    avg_python = np.mean([ct['solve_cilp'] + ct['extract_join'] +
                         ct['convert_output'] for ct in all_timings])
    avg_other = np.mean([ct['other'] + ct['duckdb_connection']
                        for ct in all_timings])
    avg_total = avg_load + avg_total_count + \
        avg_filter + avg_calc + avg_python + avg_other

    data_loading = avg_load  # This is the mixed operation
    count_query = avg_total_count
    go_processing = avg_filter + avg_calc

    print(f"\nAverage time per case: {avg_total:.1f}s")
    print(
        f"\n🔴 DATA LOADING (mixed operation): {data_loading:.1f}s ({data_loading/avg_total*100:.1f}%)")
    print(f"   This includes (inseparable in current implementation):")
    print(f"   - DuckDB: Scanning cells table")
    print(f"   - DuckDB: Filtering WHERE value IN (...)")
    print(f"   - Network: Transferring result set")
    print(f"   - Go: Creating bitmap data structures")
    print(
        f"\n🟠 DUCKDB COUNT QUERY: {count_query:.1f}s ({count_query/avg_total*100:.1f}%)")
    print(f"   Pure database operation: SELECT COUNT(DISTINCT table_id)")
    print(
        f"\n🔵 GO IN-MEMORY PROCESSING: {go_processing:.1f}s ({go_processing/avg_total*100:.1f}%)")
    print(
        f"   - Filter Bitmaps: {avg_filter:.1f}s ({avg_filter/avg_total*100:.1f}%)")
    print(
        f"   - Calculations (pair/quad/PMI): {avg_calc:.1f}s ({avg_calc/avg_total*100:.1f}%)")
    print(
        f"\n🟢 PYTHON SERVICE: {avg_python:.1f}s ({avg_python/avg_total*100:.1f}%)")
    print(f"   CILP solver, join extraction, output conversion")
    print(
        f"\n⚪ CONNECTION OVERHEAD: {avg_other:.1f}s ({avg_other/avg_total*100:.1f}%)")

    print("\n" + "="*80)
    print("PRIMARY BOTTLENECK ANALYSIS")
    print("="*80)
    print(
        f"The 'Data Loading' operation ({data_loading:.1f}s, {data_loading/avg_total*100:.1f}%) is likely dominated by:")
    print(
        f"  • DuckDB table scan (probably 70-80% of the {data_loading:.1f}s)")
    print(f"  • Network transfer (probably 10-20%)")
    print(f"  • Bitmap creation in Go (probably 5-10%)")
    print(f"\nTo optimize, focus on:")
    print(f"  1. DuckDB table indexing on 'value' column")
    print(f"  2. Query optimization (batch queries, caching)")
    print(f"  3. Network bandwidth if transferring many rows")

    # Find cases with highest data loading overhead
    loading_times = [(ct['case'], ct['load_bitmaps'] + ct['total_count'])
                     for ct in all_timings]
    loading_times.sort(key=lambda x: x[1], reverse=True)

    print("\n" + "="*80)
    print("Cases with highest data loading overhead (targets for optimization):")
    for i, (case, time) in enumerate(loading_times[:5], 1):
        print(f"   {i}. Case {case}: {time:.1f}s")

    print("\n" + "="*80)
    print(f"All bottleneck visualizations saved to: {output_dir}")
    print("="*80)


if __name__ == "__main__":
    main()
