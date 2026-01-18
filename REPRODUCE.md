# Benchmark Reproduction

This document provides detailed instructions for reproducing the benchmark results.

## Hardware Specifications

### System Configuration
- **CPU**: Intel Core i5-13600K (14 cores: 6 P-cores @ 3.5-5.1 GHz + 8 E-cores @ 2.6-3.9 GHz, 20 threads)
- **GPU**: NVIDIA GeForce RTX 3070 (8 GB VRAM)
- **RAM**: 32 GB DDR4 @ 3200 MHz
- **Storage**: 1 TB NVMe M.2 SSD
- **Operating System**: Ubuntu 24.04 LTS (kernel 6.8.0-90-generic)

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
- **uv** - Python package manager
  ```bash
  # Install uv
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Ollama** - Local LLM runtime (see AI Benchmarking section for installation)

---

# Benchmarking (RS JP with Top K=1 and CS JP LP)

**Note on Benchmark Execution:**
- **Wiki Tables and Git Tables**: Benchmarks were run on a local machine (see Hardware Specifications above)
- **WDC Tables (Vertica)**: Benchmarks were run on the big-dama-2 server due to resource requirements
  - Some cases (e.g., Case 10) are too resource-heavy for local execution
  - Most cases can run locally, but larger cases may require server resources

## Reproduction Steps

### 1. Setup Environment

#### Option A: DuckDB (Wiki Tables or Git Tables)

```bash
# Clone the repository and checkout duckdb-only branch
git clone https://github.com/tub-lsdi/bitmap-approach.git
cd bitmap-approach
git checkout vertica-only
```

Download one of the following corpus databases:

1. **Wiki Corpus**: https://tubcloud.tu-berlin.de/s/XYDeqCGcC25pWKg
2. **Git Tables Corpus**: https://tubcloud.tu-berlin.de/s/y7rYRZR74ECAjs3

The downloaded files are .zip archives. Extract them first, then rename the extracted database file to `corpus.db` and place it in the project root folder for the services to locate it.

```bash
# For Wiki Tables benchmarks:
unzip /path/to/downloaded_wiki_corpus.zip
mv wiki_corpus.db corpus.db

# OR for Git Tables benchmarks:
unzip /path/to/downloaded_git_tables_corpus.zip
mv gittables_corpus.db corpus.db
```

#### Option B: Vertica WDC Corpus

**Prerequisites:** Access to big-dama-2.dima.tu-berlin.de server

```bash
# SSH into the server
ssh username@big-dama-2.dima.tu-berlin.de

# Clone the repository and checkout vertica-only branch
git clone https://github.com/tub-lsdi/bitmap-approach.git
cd bitmap-approach
git checkout vertica-only
```

Create a `.env` file in the project root:

```bash
# Vertica Database Connection
VERTICA_HOST="YOUR_VERTICA_HOST"
VERTICA_PORT=YOUR_VERTICA_PORT
VERTICA_DATABASE="YOUR_DATABASE_NAME"
VERTICA_USERNAME="YOUR_USERNAME"
VERTICA_PASSWORD="YOUR_PASSWORD"

# Go Server Configuration (internal Docker port)
SERVER_PORT=8080

# Benchmark Configuration
RESULTS_DIR="/home/YOUR_USERNAME/bitmap-approach/results"
```

**Important:** Replace placeholders with your actual Vertica credentials and adjust `RESULTS_DIR` to match your user directory on the server (e.g., `/home/lsdi_semajoin/code/bitmap-approach/results`).

### 2. Build Docker Images
```bash
make build
```

**Expected Output:**
- Go service Docker image built successfully
- Python service Docker image built with dependencies (PuLP, HiGHS, loguru, requests, numpy)

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
  "start_time": "2026-01-13T14:43:39.260237",
  "start_time_berlin": "2026-01-13T15:43:39.260237+01:00",
  "end_time": "2026-01-13T15:12:45.123456",
  "total_duration_seconds": 1745.86,
  "database": "duckdb",
  "total_cases": 49,
  "successful_cases": 49,
  "failed_cases": 0,
  "average_duration_seconds": 35.63,
  "median_duration_seconds": 28.45,
  "results": [
    {
      "case_number": 1,
      "success": true,
      "duration_seconds": 12.34,
      "error": null,
      "start_time": "2026-01-13T14:43:39.260237",
      "end_time": "2026-01-13T14:43:51.604321",
      "output": {
        "mappings": [
          {"r_val": "dover", "s_val": "delaware", "npmi": 0.85}
        ],
        "num_r": 201,
        "num_s": 201,
        "num_mappings": 8
      },
      "go_service_timings": {
        "duckdb_connection": {
          "start_time": "2026-01-13T14:43:39.270000",
          "end_time": "2026-01-13T14:43:39.320000",
          "duration_seconds": 0.05
        },
        "load_and_create_bitmaps": {
          "start_time": "2026-01-13T14:43:39.320000",
          "end_time": "2026-01-13T14:43:47.440000",
          "duration_seconds": 8.12
        },
        "filter_bitmaps": {
          "start_time": "2026-01-13T14:43:47.440000",
          "end_time": "2026-01-13T14:43:49.780000",
          "duration_seconds": 2.34
        },
        "get_total_table_count": {
          "start_time": "2026-01-13T14:43:49.780000",
          "end_time": "2026-01-13T14:43:49.790000",
          "duration_seconds": 0.01
        },
        "calculate_pmi_scores": {
          "start_time": "2026-01-13T14:43:49.790000",
          "end_time": "2026-01-13T14:43:51.020000",
          "duration_seconds": 1.23
        }
      },
      "python_service_timings": {
        "step1_solve_cilp": 0.45,
        "step2_extract_join": 0.03,
        "step3_convert_output": 0.01,
        "total_duration": 0.49
      }
    }
  ]
}
```


### Missing Case 13
Case 13 is intentionally excluded from all benchmarks.

---

# Benchmarking (RS JP with Top K=5 & Large Language Model - Naive Approach)

**The Problem:** The RS-JP with Top K=5 algorithm returns up to 5 candidate matches for each value based on statistical correlation (NPMI scores). For example, given "dover", it might return candidates like ["delaware", "kentucky", "maryland"]. But which one should actually be used for the join?

**The Solution:** This mode uses a large language model (via Ollama) to evaluate the semantic relationships between values and select the single best match. The AI understands context like:
- "dover" → "delaware" (Dover is the capital of Delaware)
- "phoenix" → "arizona" (Phoenix is a city in Arizona)
- "moon" → "earth" (Moon is Earth's satellite)

**How It Works:** You provide an existing RS-JP benchmark JSON file as input. For each value that has multiple candidates, the AI evaluates them and picks the most semantically appropriate match, providing an explanation for its choice.

## Prerequisites

**IMPORTANT:** Before running AI benchmarking, you must first generate RS-JP results with `top_k=5` (instead of the default `top_k=1`).

### Adjust top_k Parameter

1. Open the file `python-service/benchmark_rs_jp.py`
2. Find the line (around line 132):
   ```python
   bridge_table, python_timings = algorithm.create_bridge(
       list_r_normalized, list_s_normalized, pmi_scores, top_k=1
   )
   ```
3. Change `top_k=1` to `top_k=5`:
   ```python
   bridge_table, python_timings = algorithm.create_bridge(
       list_r_normalized, list_s_normalized, pmi_scores, top_k=5
   )
   ```

### Generate RS-JP Benchmark with top_k=5

After adjusting the parameter, rebuild and start the services:

```bash
# Rebuild Docker images with the updated code
make build

# Start services
make up

# Run RS-JP benchmark with top_k=5
./benchmark.sh rs_jp 1 50
```

This will generate a benchmark JSON file in `results/benchmark_rs_jp_duckdb_YYYYMMDD_HHMMSS.json` that contains up to 5 candidates per value, which can then be used as input for AI benchmarking.

**Note:** Remember to change `top_k` back to `1` if you want to run the standard RS-JP benchmark later (and rebuild with `make build`).

## Reproduction Steps

### 1. Install Ollama

Download and install Ollama from [ollama.com](https://ollama.com) or use:

```bash
# Linux
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull Ollama Model

For AI benchmarking, we use **Mistral 7B** - a 7 billion parameter model that provides good performance for semantic evaluation tasks.

**Model Information:**
- **Model**: Mistral 7B v0.3 (mistral:latest points to 7B as of 14.01.2026)
- **Size**: 4.4 GB
- **Parameters**: 7B
- **Context Window**: 32K tokens

```bash
# Pull mistral model (latest tag points to 7B)
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

### 4. Run AI Benchmarking (Naive)

In your main terminal (from project root), run:

```bash
./benchmark.sh ai_naiv -i <path_to_benchmark_json>
```

**Example:**
```bash
# Evaluate Wiki Tables RS-JP benchmark
./benchmark.sh ai_naiv -i eval-result-data/duckdb_wiki_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_154339.json

# Evaluate Git Tables RS-JP benchmark
./benchmark.sh ai_naiv -i eval-result-data/duckdb_git_tables_bench/rs_jp_top_k_5/benchmark_rs_jp_duckdb_20260113_155003.json
```

**Expected Output:**
```
Running AI benchmarking mode (Naive)
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

**What This Does:**
1. Loads the RS-JP benchmark results from the specified JSON file
2. For each r_val with multiple s_val candidates, queries the Ollama AI model directly
3. AI evaluates semantic relationships and selects the most appropriate match (single-step, no context determination)
4. Saves results with AI's choices and explanations to `results/` directory

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
      "benchmark_start_time": "2026-01-13T14:43:39.260237",
      "benchmark_total_cases": 49,
      "benchmark_successful_cases": 49
    },
    "ai_evaluation": {
      "total_cases": 49,
      "cases_processed": 47,
      "cases_skipped": 0,
      "total_r_vals_processed": 4640,
      "total_duration_seconds": 1234.56,
      "model_used": "mistral:latest",
      "timestamp": "20260114_132612",
      "input_file": "/path/to/benchmark_rs_jp_duckdb_YYYYMMDD_HHMMSS.json",
      "output_file": "/path/to/results/ai_evaluation_results_YYYYMMDD_HHMMSS.json"
    }
  },
  "cases": [
    {
      "case_number": 1,
      "num_r_vals": 188,
      "mappings": [
        {
          "r_val": "algeria",
          "s_vals": ["africa"],
          "chosen_s_val": "africa",
          "raw_ai_response": null,
          "ai_explanation": null,
          "ai_duration_seconds": 0,
          "ai_success": true,
          "ai_error": null,
          "ai_called": false
        },
        {
          "r_val": "dover",
          "s_vals": ["delaware", "kentucky"],
          "chosen_s_val": "delaware",
          "raw_ai_response": "{\"r_val\": \"dover\", \"s_val\": \"delaware\", \"explanation\": \"...\"}",
          "ai_explanation": "Dover is the capital city of Delaware",
          "ai_duration_seconds": 1.26,
          "ai_success": true,
          "ai_error": null,
          "ai_called": true
        }
      ],
      "total_duration_seconds": 18.72,
      "case_had_mappings": true
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
./benchmark.sh ai_naiv -i <input_file> [-m model] [-o output_dir] [--ollama-host host]
```

---

# Benchmarking (RS JP with Top K=5 & Large Language Model - Context Approach)

This approach provides better accuracy by first understanding the semantic relationship between lists before making matching decisions.

**Differences from Naive Approach:**
- Two-step AI query: (1) Context determination, (2) Matching with context
- Random sampling: 100 rows from each list to determine context
- Reproducible: Uses random seed 42
- Better accuracy: AI has domain understanding before matching

## Prerequisites

Same as naive approach above (Ollama installed, model pulled, server running), plus:
- RS-JP benchmark results with `top_k=5` (see previous section)
- `benchmark-data/` directory with case input files (Case1_input.txt, etc.)

## Reproduction Steps

### 1. Ensure Prerequisites Are Met

Make sure you have:
- Ollama server running (see previous section)
- Mistral model pulled (`ollama pull mistral:latest`)
- RS-JP results with top_k=5 generated
- `benchmark-data/` directory in project root

### 2. Run Context-Enhanced AI Benchmarking

**Command:**
```bash
./benchmark.sh ai -i <path_to_benchmark_json> --random-seed 42
```

**Example:**
```bash
# Evaluate Wiki Tables RS-JP benchmark
./benchmark.sh ai \
  -i results/benchmark_rs_jp_duckdb_20260113_154339.json \
  --random-seed 42

# Evaluate Git Tables RS-JP benchmark
./benchmark.sh ai \
  -i results/benchmark_rs_jp_duckdb_20260113_155003.json \
  --random-seed 42
```

**Note:** Use `--random-seed 42` to reproduce the benchmark results. This ensures the same random sample of 100 rows is selected for context determination.

### 3. Expected Output

```
Running AI benchmarking mode (Context)
================================================================================
Benchmark AI RS-JP Evaluation (Context)
================================================================================
Input file: /path/to/benchmark_file.json
Output file: /path/to/results/ai_evaluation_results_20260114_HHMMSS.json
Benchmark data dir: /path/to/benchmark-data
Ollama model: mistral:latest
Ollama API: http://0.0.0.0:11434
Using random seed: 42
================================================================================

Loading benchmark file...
Loaded 49 cases

Processing cases...
[1/49] Processing case #1 (success=True)...
  Querying AI for join context (List R: 100 rows sampled from 201, List S: 100 rows sampled from 201)...
  ✓ Context determined: cities to states
  Querying AI for r_val='dover' with 2 candidate(s)...
  ✓ AI chose 'delaware' (explanation: Dover is the capital city of Delaware...)
  ✓ Completed in 32.45 seconds
    Processed 8 r_val(s)
    Context: cities to states
...
```

**What This Does:**
1. For each case, loads the corresponding input file (e.g., `Case1_input.txt`)
2. Randomly samples 100 rows from List R and 100 rows from List S (using seed 42)
3. Sends samples to AI to determine the semantic relationship
4. For each r_val with multiple candidates, uses the context to make informed decisions
5. Saves results with context information to `results/` directory

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
      "benchmark_start_time": "2026-01-13T14:43:39.260237",
      "benchmark_total_cases": 49,
      "benchmark_successful_cases": 49
    },
    "ai_evaluation": {
      "total_cases": 49,
      "cases_processed": 47,
      "cases_skipped": 0,
      "total_r_vals_processed": 4640,
      "context_queries_successful": 47,
      "total_duration_seconds": 1970.85,
      "model_used": "mistral:latest",
      "timestamp": "20260114_132612",
      "input_file": "/path/to/benchmark_rs_jp_duckdb_YYYYMMDD_HHMMSS.json",
      "output_file": "/path/to/results/ai_evaluation_results_YYYYMMDD_HHMMSS.json",
      "benchmark_data_dir": "/path/to/benchmark-data",
      "random_seed": 42,
      "sampling_method": "random"
    }
  },
  "cases": [
    {
      "case_number": 1,
      "num_r_vals": 188,
      "mappings": [
        {
          "r_val": "algeria",
          "s_vals": ["africa"],
          "chosen_s_val": "africa",
          "raw_ai_response": null,
          "ai_explanation": null,
          "ai_duration_seconds": 0,
          "ai_success": true,
          "ai_error": null,
          "ai_called": false
        },
        {
          "r_val": "dover",
          "s_vals": ["delaware", "kentucky"],
          "chosen_s_val": "delaware",
          "raw_ai_response": "{\"r_val\": \"dover\", \"s_val\": \"delaware\", \"explanation\": \"...\"}",
          "ai_explanation": "Dover is the capital city of Delaware",
          "ai_duration_seconds": 1.26,
          "ai_success": true,
          "ai_error": null,
          "ai_called": true
        }
      ],
      "total_duration_seconds": 24.93,
      "case_had_mappings": true,
      "context_query": {
        "context_info": {
          "relationship_type": "cities to states",
          "list_r_description": "List R contains city names",
          "list_s_description": "List S contains state names",
          "join_context": "Each city should be matched to its home state"
        },
        "raw_response": "{\"relationship_type\": \"cities to states\", ...}",
        "duration_seconds": 2.14,
        "success": true,
        "error": null
      }
    }
  ]
}
```

## Command Options Reference

**Required Options:**
- `-i, --input FILE`: Path to benchmark JSON file (required)

**Optional Options:**
- `-m, --model MODEL`: Ollama model to use (default: `mistral:latest`)
- `-o, --output-dir DIR`: Output directory (default: `<project_root>/results`)
- `--ollama-host HOST`: Ollama API host (default: `http://0.0.0.0:11434`)
- `--benchmark-data-dir DIR`: Benchmark data directory (default: `<project_root>/benchmark-data`)
- `--random-seed SEED`: Random seed (default: none, but use 42 for reproducibility)

**Full Command Format:**
```bash
./benchmark.sh ai -i <input_file> --random-seed 42 [-m model] [-o output_dir] [--ollama-host host] [--benchmark-data-dir dir]
```
