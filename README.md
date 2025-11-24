# Bitmap Approach

This project implements a bitmap-based approach for calculating quad scores from DuckDB data.

## Prerequisites

- Go 1.24.0 or later
- DuckDB database file
- Environment configuration file (`.env`)

## Setup

### 1. Environment Configuration

Create a `.env` file in the project root directory. You can use `.env.template` as a reference:

```bash
cp .env.template .env
```

Edit `.env` and set the path to your DuckDB database file:

```
DUCKDB_PATH=path/to/your/duckdb/file.db
```

**Important:** The `.env` file is required for both programs to run. Make sure it exists and contains a valid `DUCKDB_PATH` before running any commands.

### 2. Build Binaries

The binaries are already compiled in the `bin/` directory. If you need to rebuild them:

```bash
go build -o bin/prototype ./cmd/prototype
go build -o bin/benchmark ./cmd/benchmark
```

## Usage

### Prototype Program

The prototype program calculates quad scores for a specific case from the benchmark data.

**Usage:**
```bash
./bin/prototype -case <case_number>
```

**Example:**
```bash
./bin/prototype -case 1
```

**Flags:**
- `-case` (required): Case number to load lists from (e.g., '1' for Case1_input.txt)

**Output:**
The program will:
1. Load ListR and ListS from the specified case file
2. Connect to DuckDB using the path from `.env`
3. Fetch relevant table IDs
4. Load table rows from DuckDB
5. Calculate quad scores
6. Display the top 20 quadruples with their counts

### Benchmark Program

The benchmark program runs the prototype program across multiple test cases and generates performance reports.

**Usage:**
```bash
./bin/benchmark [flags]
```

**Flags:**
- `-timeout` (default: 60): Maximum execution time per case in seconds
- `-program` (default: "prototype"): Program to benchmark (must exist in `bin/` directory)
- `-results` (default: "results"): Directory to store results
- `-format` (default: "json"): Output format: json or csv
- `-start` (default: 1): Starting case number
- `-end` (default: 50): Ending case number

**Examples:**
```bash
# Run benchmark for cases 1-10 with default settings
./bin/benchmark -start 1 -end 10

# Run benchmark with custom timeout and CSV output
./bin/benchmark -timeout 120 -format csv -start 1 -end 20

# Run benchmark for a specific range
./bin/benchmark -start 5 -end 15 -results my_results
```

**Output:**
The benchmark program will:
1. Run the prototype program for each case in the specified range
2. Track execution time, success/failure, and timeouts
3. Generate a summary report
4. Save results to a JSON or CSV file in the results directory

## Project Structure

```
.
├── bin/                    # Compiled binaries
│   ├── prototype          # Main prototype program
│   └── benchmark          # Benchmark runner
├── cmd/
│   ├── prototype/         # Prototype CLI code
│   └── benchmark/         # Benchmark CLI code
├── internal/
│   ├── config/            # Configuration management
│   ├── duckdb/            # DuckDB client and queries
│   ├── model/             # Data models
│   └── service/           # Business logic
├── benchmark-data/        # Test case input files
├── results/               # Benchmark results (generated)
├── .env                   # Environment configuration (create from .env.template)
└── .env.template          # Environment template

```

## Troubleshooting

**Error: DUCKDB_PATH environment variable is not set**
- Make sure you have created a `.env` file in the project root
- Verify the `.env` file contains `DUCKDB_PATH=path/to/your/duckdb/file.db`
- Check that the path points to a valid DuckDB database file

**Error: -case flag is required**
- The prototype program requires a case number to be specified
- Use `-case <number>` when running the prototype program

**Program not found errors**
- Make sure the binaries are built in the `bin/` directory
- Rebuild if necessary: `go build -o bin/prototype ./cmd/prototype`


