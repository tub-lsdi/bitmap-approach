# time comparisons cases
uv run evaluation/compare_case_durations.py --directories eval-result-data/duckdb_git_tables_bench/cs_jp_lp eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp eval-result-data/vertica_wdc_bench/cs_jp_lp --label eval-result-data/duckdb_git_tables_bench/cs_jp_lp="Git Tables" --label eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp="Wiki Tables" --label eval-result-data/vertica_wdc_bench/cs_jp_lp="WDC" --output eval_results_visualisation/times-cs-cases.png --title "Duration per Case: CS JP LP"
uv run evaluation/compare_case_durations.py --directories eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1 eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1 eval-result-data/vertica_wdc_bench/rs_jp_top_k_1 --label eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1="Git Tables" --label eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1="Wiki Tables" --label eval-result-data/vertica_wdc_bench/rs_jp_top_k_1="WDC" --output eval_results_visualisation/times-rs-cases.png --title "Duration per Case: RS JP"
uv run evaluation/compare_case_durations.py \
  --directories \
    eval-result-data/vertica_wdc_bench/rs_jp_top_k_1 \
    eval-result-data/vertica_wdc_bench/cs_jp_lp \
    eval-result-data/vertica_wdc_bench/rs_jp_ai_context \
  --label eval-result-data/vertica_wdc_bench/rs_jp_top_k_1="WDC rs_jp_top_k_1" \
  --label eval-result-data/vertica_wdc_bench/cs_jp_lp="WDC cs_jp_lp" \
  --label eval-result-data/vertica_wdc_bench/rs_jp_ai_context="WDC rs_jp_ai_context" \
  --output eval_results_visualisation/times-wdc-cases.png \
  --title "Duration per Case: WDC"
uv run evaluation/compare_case_durations.py \
--directories \
    eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1 \
    eval-result-data/duckdb_git_tables_bench/cs_jp_lp \
    eval-result-data/duckdb_git_tables_bench/rs_jp_ai_context \
--label eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1="Git Tables rs_jp_top_k_1" \
--label eval-result-data/duckdb_git_tables_bench/cs_jp_lp="Git Tables cs_jp_lp" \
--label eval-result-data/duckdb_git_tables_bench/rs_jp_ai_context="Git Tables rs_jp_ai_context" \
--output eval_results_visualisation/times-git-cases.png \
--title "Duration per Case: Git Tables"
uv run evaluation/compare_case_durations.py \
  --directories \
    eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1 \
    eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp \
    eval-result-data/duckdb_wiki_tables_bench/rs_jp_ai_context \
  --label eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1="Wiki Tables rs_jp_top_k_1" \
  --label eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp="Wiki Tables cs_jp_lp" \
  --label eval-result-data/duckdb_wiki_tables_bench/rs_jp_ai_context="Wiki Tables rs_jp_ai_context" \
  --output eval_results_visualisation/times-wiki-cases.png \
  --title "Duration per Case: Wiki Tables"

## steps
uv run evaluation/plot_timings.py eval-result-data/duckdb_git_tables_bench/cs_jp_lp eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1 eval-result-data/duckdb_git_tables_bench/rs_jp_ai_naive eval-result-data/duckdb_git_tables_bench/rs_jp_ai_context --output eval_results_visualisation/times-git_comparison-median.png --agg median --title "Median Benchmark Timings per Step: GitTables Corpus"
uv run evaluation/plot_timings.py eval-result-data/vertica_wdc_bench/rs_jp_top_k_1 eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1 eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1 --label eval-result-data/vertica_wdc_bench/rs_jp_top_k_1="WDC" --label eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1="Git Tables" --label eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1="Wiki Tables" --output eval_results_visualisation/times-rs_jp-median --agg median --title "Median Benchmark Timings per Step: RS JP"
uv run evaluation/plot_timings.py eval-result-data/vertica_wdc_bench/rs_jp_top_k_1 eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1 eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1 --label eval-result-data/vertica_wdc_bench/rs_jp_top_k_1="WDC" --label eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1="Git Tables" --label eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1="Wiki Tables" --output eval_results_visualisation/times-rs_jp-mean.png --agg mean --title "Mean Benchmark Timings per Step: RS JP"
uv run evaluation/plot_timings.py eval-result-data/vertica_wdc_bench/cs_jp_lp eval-result-data/duckdb_git_tables_bench/cs_jp_lp eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp  --label eval-result-data/duckdb_git_tables_bench/cs_jp_lp="Git Tables" --label eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp="Wiki Tables" --label eval-result-data/vertica_wdc_bench/cs_jp_lp="WDC" --output eval_results_visualisation/times-cs_jp_lp-mean.png --agg mean --title "Mean Benchmark Timings per Step: CS JP LP"
uv run evaluation/plot_timings.py eval-result-data/vertica_wdc_bench/cs_jp_lp eval-result-data/duckdb_git_tables_bench/cs_jp_lp eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp  --label eval-result-data/duckdb_git_tables_bench/cs_jp_lp="Git Tables" --label eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp="Wiki Tables" --label eval-result-data/vertica_wdc_bench/cs_jp_lp="WDC" --output eval_results_visualisation/times-cs_jp_lp-median.png --agg median --title "Median Benchmark Timings per Step: CS JP LP"

# metrics comparison
uv run evaluation/compare_metrics_to_baselines.py --baseline eval-result-data/vertica_wdc_bench/rs_jp_top_k_1/benchmark_rs_jp_vertica_wdc_20260106_233913.json  --comparison eval-result-data/vertica_wdc_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_vertica_wdc_20260118_112423.json eval-result-data/vertica_wdc_bench/rs_jp_ai_naive/benchmark_rs_jp_ai_naive_wdc_20260118_102154.json --output eval_results_visualisation/metrics-wdc_ai_comparison-percentage.png --percentage
uv run evaluation/compare_metrics_to_baselines.py --baseline eval-result-data/vertica_wdc_bench/cs_jp_lp/benchmark_cs_jp_lp_vertica_wdc_20260106_223539.json --comparison eval-result-data/vertica_wdc_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_vertica_wdc_20260118_112423.json eval-result-data/vertica_wdc_bench/rs_jp_ai_naive/benchmark_rs_jp_ai_naive_wdc_20260118_102154.json  eval-result-data/vertica_wdc_bench/rs_jp_top_k_1/benchmark_rs_jp_vertica_wdc_20260106_233913.json --output eval_results_visualisation/metrics-wdc_cs_comparison-absolute.png --absolute
uv run evaluation/compare_metrics_to_baselines.py --baseline eval-result-data/vertica_wdc_bench/cs_jp_lp/benchmark_cs_jp_lp_vertica_wdc_20260106_223539.json --comparison eval-result-data/vertica_wdc_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_vertica_wdc_20260118_112423.json eval-result-data/vertica_wdc_bench/rs_jp_ai_naive/benchmark_rs_jp_ai_naive_wdc_20260118_102154.json  eval-result-data/vertica_wdc_bench/rs_jp_top_k_1/benchmark_rs_jp_vertica_wdc_20260106_233913.json --output eval_results_visualisation/metrics-wdc_cs_comparison-percentage.png --percentage
uv run evaluation/compare_metrics_to_baselines.py --baseline eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_wiki_20260111_010822.json --comparison  eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_wiki_20260111_011005.json eval-result-data/duckdb_wiki_tables_bench/rs_jp_ai_naive/benchmark_rs_jp_ai_naive_duckdb_wiki_20260114_025120.json  eval-result-data/duckdb_wiki_tables_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_duckdb_wiki_20260114_132612.json --output eval_results_visualisation/metrics-wiki_comparison-absolute.png --absolute
uv run evaluation/compare_metrics_to_baselines.py --baseline eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_wiki_20260111_010822.json --comparison  eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_wiki_20260111_011005.json eval-result-data/duckdb_wiki_tables_bench/rs_jp_ai_naive/benchmark_rs_jp_ai_naive_duckdb_wiki_20260114_025120.json  eval-result-data/duckdb_wiki_tables_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_duckdb_wiki_20260114_132612.json --output eval_results_visualisation/metrics-wiki_comparison-percentage.png --percentage
uv run evaluation/compare_metrics_to_baselines.py --baseline eval-result-data/duckdb_git_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_git_20260111_024617.json --comparison eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_git_20260111_030706.json eval-result-data/duckdb_git_tables_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_duckdb_git_20260116_095127.json eval-result-data/duckdb_git_tables_bench/rs_jp_ai_naive/benchmark_rs_jp_ai_naive_duckdb_git_20260114_022835.json  --output eval_results_visualisation/metrics-git_comparison-absolute.png --absolute
uv run evaluation/compare_metrics_to_baselines.py --baseline eval-result-data/duckdb_git_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_git_20260111_024617.json --comparison eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_git_20260111_030706.json eval-result-data/duckdb_git_tables_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_duckdb_git_20260116_095127.json eval-result-data/duckdb_git_tables_bench/rs_jp_ai_naive/benchmark_rs_jp_ai_naive_duckdb_git_20260114_022835.json  --output eval_results_visualisation/metrics-git_comparison-percentage.png --percentage
uv run evaluation/compare_metrics_to_baselines.py --baseline eval-result-data/vertica_wdc_bench/cs_jp_lp/benchmark_cs_jp_lp_vertica_wdc_20260106_223539.json  --comparison eval-result-data/vertica_wdc_bench/rs_jp_top_k_1/benchmark_rs_jp_vertica_wdc_20260106_233913.json  eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_wiki_20260111_011005.json eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_wiki_20260111_010822.json  eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_git_20260111_030706.json eval-result-data/duckdb_git_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_git_20260111_024617.json --output eval_results_visualisation/metrics-best_vs_rest_comparison-absolute.png --absolute
uv run evaluation/compare_metrics_to_baselines.py --baseline eval-result-data/vertica_wdc_bench/cs_jp_lp/benchmark_cs_jp_lp_vertica_wdc_20260106_223539.json  --comparison eval-result-data/vertica_wdc_bench/rs_jp_top_k_1/benchmark_rs_jp_vertica_wdc_20260106_233913.json  eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_wiki_20260111_011005.json eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_wiki_20260111_010822.json  eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_git_20260111_030706.json eval-result-data/duckdb_git_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_git_20260111_024617.json --output eval_results_visualisation/metrics-best_vs_rest_comparison-percentage.png --percentage


# metrics comparison cases
uv run evaluation/compare_metrics_per_case.py \
  --groundtruth_dir benchmark-data \
  --results_dir . \
  --files \
    eval-result-data/vertica_wdc_bench/cs_jp_lp/benchmark_cs_jp_lp_vertica_wdc_20260106_201044.json \
    eval-result-data/vertica_wdc_bench/rs_jp_top_k_1/benchmark_rs_jp_vertica_wdc_20260106_233913.json \
    eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_wiki_20260111_010822.json \
    eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_wiki_20260111_011005.json \
    eval-result-data/duckdb_git_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_git_20260111_024617.json \
    eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_git_20260111_030706.json \
  --label eval-result-data/vertica_wdc_bench/cs_jp_lp/benchmark_cs_jp_lp_vertica_wdc_20260106_201044.json="WDC CS JP LP" \
  --label eval-result-data/vertica_wdc_bench/rs_jp_top_k_1/benchmark_rs_jp_vertica_wdc_20260106_233913.json="WDC RS JP" \
  --label eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_wiki_20260111_010822.json="Wiki CS JP LP" \
  --label eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_wiki_20260111_011005.json="Wiki RS JP" \
  --label eval-result-data/duckdb_git_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_git_20260111_024617.json="Git CS JP LP" \
  --label eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_git_20260111_030706.json="Git RS JP" \
  --plot heatmap \
  --no-table \
  --output eval_results_visualisation/metrics-corpora-heatmap.png
uv run evaluation/compare_metrics_per_case.py \
--groundtruth_dir benchmark-data \
--results_dir . \
--files \
    eval-result-data/vertica_wdc_bench/cs_jp_lp/benchmark_cs_jp_lp_vertica_wdc_20260106_201044.json \
    eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_wiki_20260111_010822.json \
    eval-result-data/duckdb_git_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_git_20260111_024617.json \
--label eval-result-data/vertica_wdc_bench/cs_jp_lp/benchmark_cs_jp_lp_vertica_wdc_20260106_201044.json="WDC CS JP LP" \
--label eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_wiki_20260111_010822.json="Wiki CS JP LP" \
--label eval-result-data/duckdb_git_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_git_20260111_024617.json="Git CS JP LP" \
--plot heatmap \
--no-table \
--output eval_results_visualisation/metrics-cs_jp_lp-heatmap.png

uv run evaluation/compare_metrics_per_case.py \                                                                                                                                ─╯
  --groundtruth_dir benchmark-data \
  --results_dir . \
  --files \
    eval-result-data/vertica_wdc_bench/rs_jp_top_k_1/benchmark_rs_jp_vertica_wdc_20260106_233913.json \
    eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_wiki_20260111_011005.json \
    eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_git_20260111_030706.json \
  --label eval-result-data/vertica_wdc_bench/rs_jp_top_k_1/benchmark_rs_jp_vertica_wdc_20260106_233913.json="WDC RS JP" \
  --label eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_wiki_20260111_011005.json="Wiki RS JP" \
  --label eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_git_20260111_030706.json="Git RS JP" \
  --plot heatmap \
  --no-table \
  --output eval_results_visualisation/metrics-rs_jp-heatmap.png

uv run evaluation/compare_metrics_per_case.py \
  --groundtruth_dir benchmark-data \
  --results_dir . \
  --files \
    eval-result-data/vertica_wdc_bench/cs_jp_lp/benchmark_cs_jp_lp_vertica_wdc_20260106_201044.json \
    eval-result-data/vertica_wdc_bench/rs_jp_top_k_1/benchmark_rs_jp_vertica_wdc_20260106_233913.json \
    eval-result-data/vertica_wdc_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_vertica_wdc_20260118_234546.json \
    eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_wiki_20260111_010822.json \
    eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_wiki_20260111_011005.json \
    eval-result-data/duckdb_wiki_tables_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_duckdb_wiki_20260116_130023.json \
    eval-result-data/duckdb_git_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_git_20260111_024617.json \
    eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_git_20260111_030706.json \
    eval-result-data/duckdb_git_tables_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_duckdb_git_20260116_120519.json \
  --label eval-result-data/vertica_wdc_bench/cs_jp_lp/benchmark_cs_jp_lp_vertica_wdc_20260106_201044.json="WDC CS JP LP" \
  --label eval-result-data/vertica_wdc_bench/rs_jp_top_k_1/benchmark_rs_jp_vertica_wdc_20260106_233913.json="WDC RS JP" \
  --label eval-result-data/vertica_wdc_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_vertica_wdc_20260118_234546.json="WDC AI Context" \
  --label eval-result-data/duckdb_wiki_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_wiki_20260111_010822.json="Wiki CS JP LP" \
  --label eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_wiki_20260111_011005.json="Wiki RS JP" \
  --label eval-result-data/duckdb_wiki_tables_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_duckdb_wiki_20260116_130023.json="Wiki AI Context" \
  --label eval-result-data/duckdb_git_tables_bench/cs_jp_lp/benchmark_cs_jp_lp_duckdb_git_20260111_024617.json="Git CS JP LP" \
  --label eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_1/benchmark_rs_jp_duckdb_git_20260111_030706.json="Git RS JP" \
  --label eval-result-data/duckdb_git_tables_bench/rs_jp_ai_context/benchmark_rs_jp_ai_context_duckdb_git_20260116_120519.json="Git AI Context" \
  --plot heatmap \
  --no-table \
  --output eval_results_visualisation/metrics-cs-rs-ai_context-heatmap.png
