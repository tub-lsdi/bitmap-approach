# Benchmark Reproduction

This document provides detailed instructions for reproducing the benchmark results.

## Hardware Specifications

### Test System Configuration
- **CPU**: Intel Core i5-13600K (14 cores: 6 P-cores @ 3.5-5.1 GHz + 8 E-cores @ 2.6-3.9 GHz, 20 threads)
- **GPU**: NVIDIA GeForce RTX 3070 (8 GB VRAM)
- **RAM**: 32 GB DDR4 @ 3200 MHz
- **Storage**: 1 TB NVMe M.2 SSD
- **Operating System**: Linux (Ubuntu/Debian-based)

## Prerequisites

### Required Software

**For Benchmarking (RS-JP, CS-JP-LP):**
- **Docker** - Container platform for running services
  ```bash
  # Install Docker (Linux)
  curl -fsSL https://get.docker.com -o get-docker.sh
  sudo sh get-docker.sh
  ```
- **Docker Compose** - Multi-container orchestration (usually included with Docker)
- **Make** - Build automation tool (typically pre-installed on Linux)
  ```bash
  # Verify installation
  make --version
  ```

**For AI Benchmarking:**
- **Python 3** - Python runtime (version 3.10+)
- **uv** - Fast Python package manager
  ```bash
  # Install uv
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Ollama** - Local LLM runtime (see AI Benchmarking section for installation)

### Required Files
1. `corpus.db` - Either Wiki Tables or Git Tables database (must be named `corpus.db` and placed in project root)
2. `benchmark-data/` - Directory containing 50 test cases:
   - `Case1_input.txt` through `Case50_input.txt` (excluding Case13)
   - `Case1_groundtruth.txt` through `Case50_groundtruth.txt` (for evaluation)

---

# Benchmarking (RS JP with Top K=1 and CS JP LP)

## Reproduction Steps

### 1. Build Docker Images
```bash
make build
```

**Expected Output:**
- Go service Docker image built successfully
- Python service Docker image built with dependencies (PuLP, HiGHS, loguru, requests, numpy)

### 2. Prepare Corpus Database

Before starting services, ensure the correct corpus database is named `corpus.db` in the project root:

```bash
# For Wiki Tables benchmarks:
cp /path/to/wiki_tables.db corpus.db

# OR for Git Tables benchmarks:
cp /path/to/git_tables.db corpus.db
```

**Important:** The database file MUST be named `corpus.db` for the services to locate it.

### 3. Start Services
```bash
make up
```

**Expected Output:**
- `bitmap-go-service` container running on port 8080
- Python service container ready for benchmark execution

**Verify Services:**
```bash
docker ps
# Should show: bitmap-go-service (healthy)
```

### 4. Run Complete Benchmark
```bash
./benchmark.sh both 1 50
```

**What This Does:**
1. Runs CS-JP-LP algorithm on Cases 1-50 (excluding Case 13)
2. Runs RS-JP algorithm on Cases 1-50 (excluding Case 13)
3. Saves results to `results/` directory

**Output Files:**
- `results/benchmark_cs_jp_lp_duckdb_YYYYMMDD_HHMMSS.json`
- `results/benchmark_rs_jp_duckdb_YYYYMMDD_HHMMSS.json`

### 5. Run Individual Algorithms (Optional)

**CS-JP-LP Only:**
```bash
./benchmark.sh cs_jp_lp 1 50
```

**RS-JP Only:**
```bash
./benchmark.sh rs_jp 1 50
```

**Custom Range:**
```bash
# Run first 10 cases only
./benchmark.sh both 1 10

# Run cases 20-30
./benchmark.sh both 20 30
```

## Output Structure

### Benchmark JSON Format
```json
{
  "algorithm": "cs_jp_lp" | "rs_jp",
  "database": "duckdb",
  "start_time": "ISO 8601 timestamp",
  "start_time_berlin": "ISO 8601 timestamp (Europe/Berlin)",
  "end_time": "ISO 8601 timestamp",
  "total_duration_seconds": 1234.56,
  "total_cases": 49,
  "successful_cases": 49,
  "failed_cases": 0,
  "average_duration_seconds": 25.19,
  "median_duration_seconds": 18.45,
  "results": [
    {
      "case_number": 1,
      "success": true,
      "duration_seconds": 12.34,
      "start_time": "ISO 8601 timestamp",
      "end_time": "ISO 8601 timestamp",
      "go_service_timings": {
        "duckdb_connection": {"duration_seconds": 0.05},
        "load_and_create_bitmaps": {"duration_seconds": 8.12},
        "filter_bitmaps": {"duration_seconds": 2.34},
        "get_total_table_count": {"duration_seconds": 0.01},
        "calculate_pmi_scores": {"duration_seconds": 1.23}
      },
      "python_service_timings": {
        "step1_solve_cilp": 0.45,
        "step2_extract_join": 0.03,
        "step3_convert_output": 0.01,
        "total_duration": 0.49
      },
      "output": {
        "mappings": [
          {"r_val": "example", "s_val": "matched", "npmi": 0.85}
        ],
        "num_r": 10,
        "num_s": 15,
        "num_mappings": 8
      }
    }
  ]
}
```

### Timing Breakdown

**CS-JP-LP Timing Components:**
- Go Service: DuckDB query + bitmap operations + PMI calculation
- Python Service: Linear Programming, extraction, formatting

**RS-JP Timing Components:**
- Go Service: DuckDB query + bitmap operations + NPMI calculation (row-level)
- Python Service: Grouping + top-k selection

### Missing Case 13
Case 13 is intentionally excluded from all benchmarks.

---

# Benchmarking (RS JP with Top K=5 & Large Language Model)

**The Problem:** The RS-JP with Top K=5 algorithm returns up to 5 candidate matches for each value based on statistical correlation (NPMI scores). For example, given "dover", it might return candidates like ["delaware", "kentucky", "maryland"]. But which one should actually be used for the join?

**The Solution:** This mode uses a large language model (via Ollama) to evaluate the semantic relationships between values and select the single best match. The AI understands context like:
- "dover" → "delaware" (Dover is the capital of Delaware)
- "phoenix" → "arizona" (Phoenix is a city in Arizona)
- "moon" → "earth" (Moon is Earth's satellite)

**How It Works:** You provide an existing RS-JP benchmark JSON file as input. For each value that has multiple candidates, the AI evaluates them and picks the most semantically appropriate match, providing an explanation for its choice.

## Reproduction Steps

### 1. Install Ollama

Download and install Ollama from [ollama.com](https://ollama.com) or use:

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull Ollama Model

```bash
# Pull mistral model (recommended)
ollama pull mistral:latest

# Verify installation
ollama list
```

**Expected Output:**
```
NAME              ID              SIZE      MODIFIED
mistral:latest    6577803aa9a0    4.4 GB    X days ago
```

### 3. Start Ollama Server

In a separate terminal, start the Ollama server:

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

**Expected Output:**
```
time=... level=INFO msg="Listening on [::]:11434 (version ...)"
time=... level=INFO msg=inference compute="..." name="..." total="X GiB" available="Y GiB"
```

**Keep this terminal running** - the Ollama server needs to stay active during AI benchmarking.

### 4. Run AI Benchmarking

In your main terminal (from project root), run:

```bash
./benchmark.sh ai -i <path_to_benchmark_json>
```

**Example:**
```bash
# Evaluate Wiki Tables RS-JP benchmark
./benchmark.sh ai -i eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_154339.json

# Evaluate Git Tables RS-JP benchmark
./benchmark.sh ai -i eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_155003.json
```

**Expected Output:**
```
Running AI benchmarking mode
================================================================================
Benchmark AI RS-JP Evaluation
================================================================================
Input file: /path/to/benchmark_file.json
Output file: /path/to/results/ai_evaluation_results_20260114_HHMMSS.json
Ollama model: mistral:latest
Ollama API: http://0.0.0.0:11434
================================================================================

Loading benchmark file...
Loaded 49 cases

Processing cases...
[1/49] Processing case #1 (success=True)...
  Querying AI for r_val='dover' with 2 candidate(s)...
  ✓ AI chose 'delaware' (explanation: Dover is the capital city of Delaware...)
  ✓ Completed in 12.34 seconds
    Processed 8 r_val(s)
...
```

**Output File:**
- `results/ai_evaluation_results_YYYYMMDD_HHMMSS.json`

## Output Structure

### Output JSON Format
```json
{
  "summary": {
    "benchmark_metadata": {
      "algorithm": "rs_jp",
      "database": "duckdb",
      "benchmark_total_cases": 49
    },
    "ai_evaluation": {
      "total_cases": 49,
      "cases_processed": 49,
      "total_r_vals_processed": 256,
      "total_duration_seconds": 1234.56,
      "model_used": "mistral:latest"
    }
  },
  "cases": [
    {
      "case_number": 1,
      "num_r_vals": 8,
      "mappings": [
        {
          "r_val": "dover",
          "s_vals": ["delaware", "kentucky"],
          "chosen_s_val": "delaware",
          "ai_explanation": "Dover is the capital city of Delaware",
          "raw_ai_response": "{...}",
          "ai_duration_seconds": 2.34,
          "ai_called": true
        }
      ],
      "total_duration_seconds": 18.72
    }
  ]
}
```

### Command Options Reference

**Available Options:**
- `-i, --input`: Path to benchmark JSON file (required)
- `-m, --model`: Ollama model to use (default: `mistral:latest`)
- `-o, --output-dir`: Output directory (default: `<project_root>/results`)
- `--ollama-host`: Ollama API host (default: `http://0.0.0.0:11434`)

**Full Command Format:**
```bash
./benchmark.sh ai -i <input_file> [-m model] [-o output_dir] [--ollama-host host]
```