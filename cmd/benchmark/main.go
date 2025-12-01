package main

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

type BenchmarkResult struct {
	CaseNumber int     `json:"case_number"`
	Success    bool    `json:"success"`
	Duration   float64 `json:"duration_seconds"`
	Timeout    bool    `json:"timeout"`
	Error      string  `json:"error,omitempty"`
	Output     string  `json:"output,omitempty"`
	StartTime  string  `json:"start_time"`
	EndTime    string  `json:"end_time"`
}

type BenchmarkRun struct {
	StartTime       string            `json:"start_time"`
	EndTime         string            `json:"end_time"`
	TotalDuration   float64           `json:"total_duration_seconds"`
	MaxTimeout      int               `json:"max_timeout_seconds"`
	Program         string            `json:"program"`
	Database        string            `json:"database"`
	TotalCases      int               `json:"total_cases"`
	SuccessfulCases int               `json:"successful_cases"`
	TimeoutCases    int               `json:"timeout_cases"`
	FailedCases     int               `json:"failed_cases"`
	AverageDuration float64           `json:"average_duration_seconds,omitempty"`
	MedianDuration  float64           `json:"median_duration_seconds,omitempty"`
	Results         []BenchmarkResult `json:"results"`
}

func main() {
	var (
		maxTimeout   = flag.Int("timeout", 60, "Maximum execution time per case in seconds")
		program      = flag.String("program", "prototype", "Program to benchmark (without cmd/ prefix)")
		resultsDir   = flag.String("results", "results", "Directory to store results")
		outputFormat = flag.String("format", "json", "Output format: json or csv")
		startCase    = flag.Int("start", 1, "Starting case number")
		endCase      = flag.Int("end", 50, "Ending case number")
	)
	flag.Parse()

	// Create results directory if it doesn't exist
	if err := os.MkdirAll(*resultsDir, 0755); err != nil {
		log.Fatalf("Failed to create results directory: %v", err)
	}

	// Get the program path
	programPath := filepath.Join("bin", *program)
	if _, err := os.Stat(programPath); os.IsNotExist(err) {
		log.Fatalf("Program not found: %s. Please build it first with 'go build -o bin/%s ./cmd/%s'", programPath, *program, *program)
	}

	// Start benchmark run
	startTime := time.Now()
	run := BenchmarkRun{
		StartTime:  startTime.Format(time.RFC3339),
		MaxTimeout: *maxTimeout,
		Program:    *program,
		Database:   "vertica",
		TotalCases: *endCase - *startCase + 1,
		Results:    make([]BenchmarkResult, 0),
	}

	fmt.Printf("Starting benchmark run at %s\n", run.StartTime)
	fmt.Printf("Program: %s\n", *program)
	fmt.Printf("Database: vertica\n")
	fmt.Printf("Cases: %d-%d\n", *startCase, *endCase)
	fmt.Printf("Max timeout per case: %d seconds\n", *maxTimeout)
	fmt.Println(strings.Repeat("=", 80))

	// Run each case
	for caseNum := *startCase; caseNum <= *endCase; caseNum++ {
		fmt.Printf("\nRunning Case %d...\n", caseNum)
		result := runCase(programPath, caseNum, *maxTimeout)
		run.Results = append(run.Results, result)

		if result.Success {
			run.SuccessfulCases++
			fmt.Printf("  ✓ Completed in %.2f seconds\n", result.Duration)
		} else if result.Timeout {
			run.TimeoutCases++
			fmt.Printf("  ✗ Timeout after %.2f seconds\n", result.Duration)
		} else {
			run.FailedCases++
			fmt.Printf("  ✗ Failed: %s\n", result.Error)
		}
	}

	// End benchmark run
	endTime := time.Now()
	run.EndTime = endTime.Format(time.RFC3339)
	run.TotalDuration = endTime.Sub(startTime).Seconds()

	// Calculate average and median for successful cases
	calculateStatistics(&run)

	// Print summary
	fmt.Println(strings.Repeat("=", 80))
	fmt.Printf("\nBenchmark Summary:\n")
	fmt.Printf("  Total cases: %d\n", run.TotalCases)
	fmt.Printf("  Successful: %d\n", run.SuccessfulCases)
	fmt.Printf("  Timeouts: %d\n", run.TimeoutCases)
	fmt.Printf("  Failed: %d\n", run.FailedCases)
	fmt.Printf("  Total duration: %.2f seconds\n", run.TotalDuration)
	if run.SuccessfulCases > 0 {
		fmt.Printf("  Average duration (successful): %.2f seconds\n", run.AverageDuration)
		fmt.Printf("  Median duration (successful): %.2f seconds\n", run.MedianDuration)
	}

	// Save results
	timestamp := startTime.Format("20060102_150405")
	var filename string
	if *outputFormat == "csv" {
		filename = filepath.Join(*resultsDir, fmt.Sprintf("benchmark_%s.csv", timestamp))
		if err := saveResultsCSV(run, filename); err != nil {
			log.Fatalf("Failed to save CSV results: %v", err)
		}
	} else {
		filename = filepath.Join(*resultsDir, fmt.Sprintf("benchmark_%s.json", timestamp))
		if err := saveResultsJSON(run, filename); err != nil {
			log.Fatalf("Failed to save JSON results: %v", err)
		}
	}

	fmt.Printf("\nResults saved to: %s\n", filename)
}

func runCase(programPath string, caseNum int, maxTimeout int) BenchmarkResult {
	caseStr := strconv.Itoa(caseNum)
	startTime := time.Now()

	// Create context with timeout
	ctx, cancel := context.WithTimeout(context.Background(), time.Duration(maxTimeout)*time.Second)
	defer cancel()

	// Create command
	cmd := exec.CommandContext(ctx, programPath, "-case", caseStr)

	// Capture output
	var stdout, stderr strings.Builder
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	// Run the command
	err := cmd.Run()
	endTime := time.Now()
	duration := endTime.Sub(startTime).Seconds()

	result := BenchmarkResult{
		CaseNumber: caseNum,
		Duration:   duration,
		StartTime:  startTime.Format(time.RFC3339),
		EndTime:    endTime.Format(time.RFC3339),
		Output:     stdout.String(),
	}

	// Check for timeout
	if ctx.Err() == context.DeadlineExceeded {
		result.Timeout = true
		result.Success = false
		result.Error = fmt.Sprintf("Timeout after %d seconds", maxTimeout)
		return result
	}

	// Check for execution error
	if err != nil {
		result.Success = false
		result.Error = err.Error()
		if stderr.Len() > 0 {
			result.Error += ": " + stderr.String()
		}
		return result
	}

	// Success
	result.Success = true
	return result
}

func saveResultsJSON(run BenchmarkRun, filename string) error {
	file, err := os.Create(filename)
	if err != nil {
		return err
	}
	defer file.Close()

	encoder := json.NewEncoder(file)
	encoder.SetIndent("", "  ")
	return encoder.Encode(run)
}

func saveResultsCSV(run BenchmarkRun, filename string) error {
	file, err := os.Create(filename)
	if err != nil {
		return err
	}
	defer file.Close()

	writer := csv.NewWriter(file)
	defer writer.Flush()

	// Write header
	header := []string{
		"case_number", "success", "duration_seconds", "timeout", "error", "start_time", "end_time",
	}
	if err := writer.Write(header); err != nil {
		return err
	}

	// Write results
	for _, result := range run.Results {
		record := []string{
			strconv.Itoa(result.CaseNumber),
			strconv.FormatBool(result.Success),
			fmt.Sprintf("%.6f", result.Duration),
			strconv.FormatBool(result.Timeout),
			result.Error,
			result.StartTime,
			result.EndTime,
		}
		if err := writer.Write(record); err != nil {
			return err
		}
	}

	// Write summary row
	writer.Write([]string{}) // Empty row
	writer.Write([]string{"SUMMARY"})
	writer.Write([]string{"start_time", run.StartTime})
	writer.Write([]string{"end_time", run.EndTime})
	writer.Write([]string{"total_duration_seconds", fmt.Sprintf("%.6f", run.TotalDuration)})
	writer.Write([]string{"max_timeout_seconds", strconv.Itoa(run.MaxTimeout)})
	writer.Write([]string{"program", run.Program})
	writer.Write([]string{"database", run.Database})
	writer.Write([]string{"total_cases", strconv.Itoa(run.TotalCases)})
	writer.Write([]string{"successful_cases", strconv.Itoa(run.SuccessfulCases)})
	writer.Write([]string{"timeout_cases", strconv.Itoa(run.TimeoutCases)})
	writer.Write([]string{"failed_cases", strconv.Itoa(run.FailedCases)})

	// Write statistics
	if run.SuccessfulCases > 0 {
		writer.Write([]string{}) // Empty row
		writer.Write([]string{"STATISTICS"})
		writer.Write([]string{"average_duration_seconds", fmt.Sprintf("%.6f", run.AverageDuration)})
		writer.Write([]string{"median_duration_seconds", fmt.Sprintf("%.6f", run.MedianDuration)})
	}

	return nil
}

// calculateStatistics computes average and median duration for successful (non-timeout) cases
func calculateStatistics(run *BenchmarkRun) {
	// Collect durations from successful cases (exclude timeouts)
	durations := make([]float64, 0, run.SuccessfulCases)
	for _, result := range run.Results {
		if result.Success && !result.Timeout {
			durations = append(durations, result.Duration)
		}
	}

	if len(durations) == 0 {
		return
	}

	// Calculate average
	sum := 0.0
	for _, d := range durations {
		sum += d
	}
	run.AverageDuration = sum / float64(len(durations))

	// Calculate median
	sort.Float64s(durations)
	n := len(durations)
	if n%2 == 0 {
		// Even number of elements: average of middle two
		run.MedianDuration = (durations[n/2-1] + durations[n/2]) / 2.0
	} else {
		// Odd number of elements: middle element
		run.MedianDuration = durations[n/2]
	}
}
