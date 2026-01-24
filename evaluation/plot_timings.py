import argparse
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.plot_style import apply_theme, get_corpus_palette
from evaluation.utils import extract_case_timings, get_short_filename, load_results


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
    parser.add_argument("files", nargs="+", help="Benchmark JSON files")
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
        "--agg",
        choices=["mean", "median"],
        default="median",
        help="Aggregation method for timings (default: median)",
    )
    args = parser.parse_args()
    apply_theme()

    file_data = []
    all_go_steps = []
    all_python_steps = []
    all_ai_steps = []

    agg_func = np.median if args.agg == "median" else np.mean

    for filepath in args.files:
        results = load_results(filepath)
        if not results:
            continue

        # Extract timings for all successful cases
        case_timings = [extract_case_timings(c) for c in results if c.get("success")]
        if not case_timings:
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

        final_avg = {
            "label": get_short_filename(filepath),
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
                label=f"Go: {step}",
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
                label=f"Py: {step}",
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
                label=f"AI: {step}",
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
    ax.set_title(f"{agg_title} Benchmark Timings per Step ({service_title})")
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
    plt.savefig(args.output, bbox_inches="tight")
    print(f"Plot saved to {args.output}")


if __name__ == "__main__":
    main()
