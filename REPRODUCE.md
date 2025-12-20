# Benchmark Reproduction

This document provides detailed instructions for reproducing the benchmark results.

## Hardware Specifications

### Test System Configuration
- **CPU**: Intel Core i5-13600K (14 cores: 6 P-cores + 8 E-cores, 20 threads)
- **GPU**: NVIDIA GeForce RTX 3070 (8 GB VRAM)
- **RAM**: 32 GB DDR4 @ 3200 MHz
- **Storage**: 1 TB NVMe M.2 SSD
- **Operating System**: Linux (Ubuntu/Debian-based)

## Prerequisites

### Required Files
1. `corpus.db` - Wiki Tables (must be in project root)
2. `benchmark-data/` - Directory containing 50 test cases:
   - `Case1_input.txt` through `Case50_input.txt` (excluding Case13)
   - `Case1_groundtruth.txt` through `Case50_groundtruth.txt` (for evaluation)

## Reproduction Steps

### 1. Build Docker Images
```bash
make build
```

**Expected Output:**
- Go service Docker image built successfully
- Python service Docker image built with dependencies (PuLP, HiGHS, loguru, requests, numpy)

### 2. Start Services
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

### 3. Run Complete Benchmark
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

### 4. Run Individual Algorithms (Optional)

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
- Python Service: Linear Programming (dominant), extraction, formatting

**RS-JP Timing Components:**
- Go Service: DuckDB query + bitmap operations + NPMI calculation (row-level)
- Python Service: Grouping + top-k selection (negligible)

### Missing Case 13
Case 13 is intentionally excluded from all benchmarks. 
