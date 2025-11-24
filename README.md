# Bitmap Approach

This project implements a bitmap-based approach for calculating quad scores from database data. It supports both DuckDB (embedded) and Vertica (client-server) databases.

## Prerequisites

- Go 1.24.0 or later
- Either:
  - DuckDB database file (for embedded database), or
  - Vertica database server (for client-server database)
- Environment configuration file (`.env`)

## Setup

### 1. Environment Configuration

Create a `.env` file in the project root directory. You can use `dotenv.template` as a reference:

```bash
cp dotenv.template .env
```

Edit `.env` and configure the database connection based on which database you want to use:

**For DuckDB (embedded database):**
```
DUCKDB_PATH=path/to/your/duckdb/file.db
```

**For Vertica (client-server database):**
```
VERTICA_HOST=localhost
VERTICA_PORT=5433
VERTICA_DATABASE=your_database
VERTICA_USERNAME=your_username
VERTICA_PASSWORD=your_password
```

**Important:** 
- The `.env` file is required for both programs to run
- For DuckDB: Set `DUCKDB_PATH` to the path of your DuckDB database file
- For Vertica: Set all Vertica connection parameters (HOST, PORT, DATABASE, USERNAME, PASSWORD)
- You only need to configure the database you plan to use, but you can configure both if you want to switch between them

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
./bin/prototype -case <case_number> [-db <database>]
```

**Examples:**
```bash
# Use DuckDB (default)
./bin/prototype -case 1

# Use Vertica
./bin/prototype -case 1 -db vertica
```

**Flags:**
- `-case` (required): Case number to load lists from (e.g., '1' for Case1_input.txt)
- `-db` (optional, default: "duckdb"): Database to use - either "duckdb" or "vertica"

**Output:**
The program will:
1. Load ListR and ListS from the specified case file
2. Connect to the selected database (DuckDB or Vertica) using configuration from `.env`
3. Fetch relevant table IDs
4. Load table rows from the database
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
│   ├── vertica/           # Vertica client and queries
│   ├── model/             # Data models (including DBClient interface)
│   └── service/           # Business logic
├── benchmark-data/        # Test case input files
├── results/               # Benchmark results (generated)
├── .env                   # Environment configuration (create from dotenv.template)
└── dotenv.template        # Environment template

```

## Troubleshooting

**Error: DUCKDB_PATH environment variable is not set**
- This error occurs when using DuckDB without configuring it
- Make sure your `.env` file contains `DUCKDB_PATH=path/to/your/duckdb/file.db`
- Check that the path points to a valid DuckDB database file

**Error: VERTICA_* environment variables are not set**
- This error occurs when using Vertica without configuring it
- Make sure your `.env` file contains all Vertica connection parameters:
  - `VERTICA_HOST`
  - `VERTICA_PORT`
  - `VERTICA_DATABASE`
  - `VERTICA_USERNAME`
  - `VERTICA_PASSWORD`
- Verify that your Vertica server is accessible and the credentials are correct

**Error: -case flag is required**
- The prototype program requires a case number to be specified
- Use `-case <number>` when running the prototype program

**Error: -db must be either 'duckdb' or 'vertica'**
- The `-db` flag only accepts "duckdb" or "vertica" as values
- Use `-db duckdb` or `-db vertica` (or omit it to use DuckDB by default)

**Program not found errors**
- Make sure the binaries are built in the `bin/` directory
- Rebuild if necessary: `go build -o bin/prototype ./cmd/prototype`

**Connection errors with Vertica**
- Verify that your Vertica server is running and accessible
- Check network connectivity to the Vertica host and port
- Ensure the database name, username, and password are correct
- Verify firewall rules allow connections to the Vertica port (default: 5433)


