import argparse
import os
import re
import sys

import matplotlib.pyplot as plt
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.plot_style import apply_theme, get_corpus_palette, save_figure
from evaluation.utils import extract_case_timings, load_results


def format_step_name(step: str) -> str:
    """
    Format step names for display:
    - Replace underscores with spaces
    - Convert step3_* to "Step 3: *"
    - Convert step2_* to "Step 2: *"
    - etc.
    """
    # Handle step*_ prefix (e.g., step3_find_tables -> Step 3: find tables)
    step_match = re.match(r"step(\d+)_(.+)", step)
    if step_match:
        step_num = step_match.group(1)
        step_name = step_match.group(2).replace("_", " ")
        return f"step {step_num}: {step_name}"

    # Default: just replace underscores with spaces
    return step.replace("_", " ")


def get_alternating_colors(n, corpus):
    colors = get_corpus_palette(corpus, n)

    # Reorder: [lightest, darkest, 2nd lightest, 2nd darkest, ...]
    alternating = []
    left, right = 0, n - 1
    while left <= right:
        alternating.append(colors[left])
        if left != right:
            alternating.append(colors[right])
        left += 1
        right -= 1

    return alternating


def main():
    parser = argparse.ArgumentParser(
        description="Plot benchmark timings as a stacked bar chart."
    )
    parser.add_argument(
        "directories",
        nargs="+",
        help="Benchmark directories containing benchmark_* JSON files",
    )
    parser.add_argument(
        "--output", default="timings_plot.png", help="Output filename for the plot"
    )
    parser.add_argument(
        "--service",
        choices=["go", "python", "ai", "all"],
        default="all",
        help="Limit plot to specific service steps",
    )
    parser.add_argument(
        "--exclude", nargs="*", default=[], help="Step names to exclude from the plot"
    )
    parser.add_argument(
        "--exclude-first-go-steps",
        action="store_true",
        help="Exclude first three go service steps: db_connection, load_and_create_bitmaps, filter_bitmaps_to_relevant_tables",
    )
    parser.add_argument(
        "--agg",
        choices=["mean", "median"],
        default="median",
        help="Aggregation method for timings (default: median)",
    )
    parser.add_argument(
        "--title",
        help="Optional title override for the plot.",
    )
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="DIR=LABEL",
        help="Override the plotted label for a directory (repeatable, e.g., /runs/expA=Experiment A).",
    )
    args = parser.parse_args()
    label_overrides = {}
    for entry in args.label:
        if "=" not in entry:
            print(f"Warning: invalid label override, expected DIR=LABEL -> {entry}")
            continue
        raw_dir, custom_label = entry.split("=", 1)
        normalized_dir = os.path.normpath(os.path.abspath(raw_dir))
        label_overrides[normalized_dir] = custom_label
    apply_theme()

    file_data = []
    all_go_steps = []
    all_python_steps = []
    all_ai_steps = []

    agg_func = np.median if args.agg == "median" else np.mean

    for dirpath in args.directories:
        if not os.path.isdir(dirpath):
            print(f"Warning: directory not found -> {dirpath}")
            continue

        benchmark_files = sorted(
            os.path.join(dirpath, f)
            for f in os.listdir(dirpath)
            if f.startswith("benchmark_") and os.path.isfile(os.path.join(dirpath, f))
        )
        if not benchmark_files:
            print(f"Warning: no benchmark_ files found in -> {dirpath}")
            continue

        case_timings = []
        for filepath in benchmark_files:
            results = load_results(filepath)
            if not results:
                continue

            case_timings.extend(
                [extract_case_timings(c) for c in results if c.get("success")]
            )

        if not case_timings:
            print(f"Warning: no valid case timings in -> {dirpath}")
            continue

        for ct in case_timings:
            go_timings = ct.get("go_service_timings", {})
            new_go_timings = {}
            for k, v in go_timings.items():
                if k in [
                    "duckdb_connection",
                    "vertica_connection",
                    "duckdb_connect",
                    "vertica_connect",
                ]:
                    new_go_timings["db_connection"] = v
                else:
                    new_go_timings[k] = v
            ct["go_service_timings"] = new_go_timings

        avg_timings = {"go": {}, "python": {}, "ai": {}}

        for ct in case_timings:
            if args.service in ["go", "all"]:
                for step in ct["go_service_timings"]:
                    if step not in all_go_steps and step not in args.exclude:
                        all_go_steps.append(step)
            if args.service in ["python", "all"]:
                for step in ct["python_service_timings"]:
                    if (
                        step != "total_duration"
                        and step not in all_python_steps
                        and step not in args.exclude
                    ):
                        all_python_steps.append(step)
            if args.service in ["ai", "all"]:
                for step in ct.get("ai_timings", {}):
                    if step not in all_ai_steps and step not in args.exclude:
                        all_ai_steps.append(step)

        # Exclude specific go service steps if specified
        if args.exclude_first_go_steps:
            steps_to_exclude = [
                "db_connection",
                "load_and_create_bitmaps",
            ]
            all_go_steps = [s for s in all_go_steps if s not in steps_to_exclude]
            print(f"Excluding go service steps: {steps_to_exclude}")

        for step in all_go_steps:
            avg_timings["go"][step] = []
        for step in all_python_steps:
            avg_timings["python"][step] = []
        for step in all_ai_steps:
            avg_timings["ai"][step] = []

        for ct in case_timings:
            for step in all_go_steps:
                avg_timings["go"][step].append(
                    ct["go_service_timings"].get(step, 0) or 0
                )
            for step in all_python_steps:
                avg_timings["python"][step].append(
                    ct["python_service_timings"].get(step, 0) or 0
                )
            for step in all_ai_steps:
                avg_timings["ai"][step].append(
                    ct.get("ai_timings", {}).get(step, 0) or 0
                )

        normalized_dirpath = os.path.normpath(os.path.abspath(dirpath))
        dir_label = label_overrides.get(
            normalized_dirpath, os.path.basename(os.path.normpath(dirpath))
        )

        final_avg = {
            "label": dir_label,
            "go": {
                step: agg_func(vals) if vals else 0
                for step, vals in avg_timings["go"].items()
            },
            "python": {
                step: agg_func(vals) if vals else 0
                for step, vals in avg_timings["python"].items()
            },
            "ai": {
                step: agg_func(vals) if vals else 0
                for step, vals in avg_timings["ai"].items()
            },
        }
        file_data.append(final_avg)

    if not file_data:
        print("No valid data found to plot.")
        return

    go_color_map = {}
    if all_go_steps:
        go_colors = get_alternating_colors(len(all_go_steps), "wdc")
        go_color_map = dict(zip(all_go_steps, go_colors))

    python_color_map = {}
    if all_python_steps:
        python_colors = get_alternating_colors(len(all_python_steps), "git")
        python_color_map = dict(zip(all_python_steps, python_colors))

    ai_color_map = {}
    if all_ai_steps:
        ai_colors = get_alternating_colors(len(all_ai_steps), "wiki")
        ai_color_map = dict(zip(all_ai_steps, ai_colors))

    fig, ax = plt.subplots(figsize=(12, 8))

    labels = [d["label"] for d in file_data]
    x = np.arange(len(labels))
    width = 0.6

    bottoms = np.zeros(len(file_data))

    if args.service in ["go", "all"]:
        for step in all_go_steps:
            values = np.array([d["go"].get(step, 0) for d in file_data])
            ax.bar(
                x,
                values,
                width,
                bottom=bottoms,
                label=f"Go: {format_step_name(step)}",
                color=go_color_map[step],
                edgecolor="white",
                linewidth=0.5,
            )
            bottoms += values

    if args.service in ["python", "all"]:
        for step in all_python_steps:
            values = np.array([d["python"].get(step, 0) for d in file_data])
            ax.bar(
                x,
                values,
                width,
                bottom=bottoms,
                label=f"Py: {format_step_name(step)}",
                color=python_color_map[step],
                edgecolor="white",
                linewidth=0.5,
            )
            bottoms += values

    if args.service in ["ai", "all"]:
        for step in all_ai_steps:
            values = np.array([d["ai"].get(step, 0) for d in file_data])
            ax.bar(
                x,
                values,
                width,
                bottom=bottoms,
                label=f"AI: {format_step_name(step)}",
                color=ai_color_map[step],
                edgecolor="white",
                linewidth=0.5,
            )
            bottoms += values

    agg_title = args.agg.capitalize()
    ax.set_ylabel(f"{agg_title} Duration (seconds)")
    service_title = (
        args.service.capitalize() if args.service != "all" else "Go, Python & AI"
    )
    plot_title = (
        args.title or f"{agg_title} Benchmark Timings per Step ({service_title})"
    )
    ax.set_title(plot_title)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(
        handles[::-1],
        labels[::-1],
        bbox_to_anchor=(1.05, 0),
        loc="lower left",
        fontsize="small",
        borderaxespad=0.0,
    )

    plt.tight_layout()
    save_figure(args.output)


if __name__ == "__main__":
    main()
