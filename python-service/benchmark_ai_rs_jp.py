import json
import requests
import time
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime


def load_benchmark_file(file_path: str) -> Dict[str, Any]:
    """Load the benchmark JSON file."""
    with open(file_path, 'r') as f:
        data = json.load(f)
    return data


def group_mappings_by_r_val(mappings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group consecutive mappings by r_val, collecting up to 5 s_val for each r_val.
    Returns a list of {r_val: str, s_vals: List[str]} dictionaries.
    """
    if not mappings:
        return []

    grouped = []
    current_r_val = None
    current_s_vals = []

    for mapping in mappings:
        r_val = mapping['r_val']
        s_val = mapping['s_val']

        if r_val != current_r_val:
            # Save previous group if it exists
            if current_r_val is not None:
                grouped.append({
                    'r_val': current_r_val,
                    's_vals': current_s_vals
                })
            # Start new group
            current_r_val = r_val
            current_s_vals = [s_val]
        else:
            # Continue current group (up to 5)
            if len(current_s_vals) < 5:
                current_s_vals.append(s_val)

    # Don't forget the last group
    if current_r_val is not None:
        grouped.append({
            'r_val': current_r_val,
            's_vals': current_s_vals
        })

    return grouped


def ask_ollama(r_val: str, s_vals: List[str], model: str = "mistral:latest") -> Dict[str, Any]:
    """
    Ask Ollama which s_val is the best match for joining with r_val.
    Returns the chosen value and timing information.
    """
    # Construct the prompt
    if len(s_vals) == 1:
        s_vals_str = f'"{s_vals[0]}"'
        s_vals_list = f'1. {s_vals[0]}'
    else:
        s_vals_str = ", ".join([f'"{s}"' for s in s_vals])
        s_vals_list = "\n".join([f'{i+1}. {s}' for i, s in enumerate(s_vals)])

    prompt = f"""You are a semantic matching system for database joins. Think critically about the relationships between values.

Target value: {r_val}

Available candidates:
{s_vals_list}

INSTRUCTIONS:
- Think critically about the SEMANTIC meaning and relationships
- Consider: Is one candidate related to, associated with, or semantically similar to "{r_val}"?
- You MUST always choose exactly ONE candidate, even if the match seems imperfect
- Base your choice on semantic similarity, contextual relationships, or domain knowledge
- If no perfect match exists, choose the semantically closest or most related option

REQUIRED OUTPUT FORMAT - JSON ONLY:
You MUST respond with ONLY valid JSON in this exact format:
{{
  "r_val": "{r_val}",
  "s_val": "your_chosen_candidate_here",
  "explanation": "explain the semantic relationship or why you chose this"
}}

CRITICAL RULES:
- Return ONLY valid JSON, no other text before or after
- The "s_val" MUST be exactly one of the candidates from the numbered list above
- Use the "explanation" field to describe your reasoning
- You CANNOT refuse to choose - selecting one candidate is MANDATORY
- Think semantically: cities→states, moons→planets, universities→locations, etc.
- Do NOT add any text outside the JSON structure

JSON Response:"""

    # Make API call to Ollama
    url = "http://0.0.0.0:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,  # Lower temperature for more deterministic responses
            "top_p": 0.9
        }
    }

    start_time = time.time()
    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        raw_response = result['response'].strip()
        duration = time.time() - start_time

        # Try to parse as JSON
        matched_val = None
        explanation = None

        try:
            # Try to extract JSON from the response
            # Sometimes the response has extra text before/after JSON
            json_start = raw_response.find('{')
            json_end = raw_response.rfind('}') + 1

            if json_start != -1 and json_end > json_start:
                json_str = raw_response[json_start:json_end]
                parsed = json.loads(json_str)

                # Extract s_val from the JSON
                chosen_s_val = parsed.get('s_val', '').strip()
                explanation = parsed.get('explanation', '')

                # Validate that chosen_s_val is one of the candidates
                for s_val in s_vals:
                    if chosen_s_val.lower() == s_val.lower():
                        matched_val = s_val
                        break

                if matched_val:
                    print(
                        f"  ✓ AI chose '{matched_val}' (explanation: {explanation[:60]}...)")
                else:
                    print(
                        f"  Warning: AI returned '{chosen_s_val}' which is not in candidates")

        except json.JSONDecodeError as e:
            print(f"  Warning: Could not parse JSON response: {e}")

        # Fallback: Try to match the raw response to one of the candidates
        if matched_val is None:
            raw_lower = raw_response.lower()

            # Check if any candidate appears in the response
            for s_val in s_vals:
                if s_val.lower() in raw_lower:
                    matched_val = s_val
                    print(
                        f"  Info: Extracted '{s_val}' from non-JSON response")
                    break

        # If still no match found, default to first value
        if matched_val is None:
            matched_val = s_vals[0]
            print(
                f"  Warning: Could not extract valid s_val from response, defaulting to '{s_vals[0]}'")
            print(f"  Raw response: {raw_response[:200]}")

        return {
            'chosen_s_val': matched_val,
            'raw_response': raw_response,
            'explanation': explanation,
            'duration_seconds': duration,
            'success': True,
            'error': None
        }
    except Exception as e:
        duration = time.time() - start_time
        print(f"  Error calling Ollama API: {e}")
        return {
            'chosen_s_val': s_vals[0],  # Default to first value if error
            'raw_response': None,
            'explanation': None,
            'duration_seconds': duration,
            'success': False,
            'error': str(e)
        }


def process_case(case: Dict[str, Any], model: str = "mistral:latest") -> Dict[str, Any]:
    """Process a single benchmark case."""
    case_number = case['case_number']
    mappings = case.get('output', {}).get('mappings', [])

    if not mappings:
        return {
            'case_number': case_number,
            'num_r_vals': 0,
            'mappings': [],
            'total_duration_seconds': 0,
            'case_had_mappings': False
        }

    # Group mappings by r_val
    grouped = group_mappings_by_r_val(mappings)

    # Process each r_val
    mappings_results = []
    case_start_time = time.time()

    for group in grouped:
        r_val = group['r_val']
        s_vals = group['s_vals']

        # If only 1 candidate, no need to ask AI
        if len(s_vals) == 1:
            print(
                f"  r_val='{r_val}' has only 1 candidate, using '{s_vals[0]}' directly (no AI call)")
            mappings_results.append({
                'r_val': r_val,
                's_vals': s_vals,
                'chosen_s_val': s_vals[0],
                'raw_ai_response': None,
                'ai_explanation': None,
                'ai_duration_seconds': 0,
                'ai_success': True,
                'ai_error': None,
                'ai_called': False
            })
        else:
            print(
                f"  Querying AI for r_val='{r_val}' with {len(s_vals)} candidate(s)...")
            ai_result = ask_ollama(r_val, s_vals, model)

            mappings_results.append({
                'r_val': r_val,
                's_vals': s_vals,
                'chosen_s_val': ai_result['chosen_s_val'],
                'raw_ai_response': ai_result['raw_response'],
                'ai_explanation': ai_result['explanation'],
                'ai_duration_seconds': ai_result['duration_seconds'],
                'ai_success': ai_result['success'],
                'ai_error': ai_result['error'],
                'ai_called': True
            })

    total_duration = time.time() - case_start_time

    return {
        'case_number': case_number,
        'num_r_vals': len(grouped),
        'mappings': mappings_results,
        'total_duration_seconds': total_duration,
        'case_had_mappings': True
    }


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Evaluate RS-JP benchmark results using Ollama AI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python benchmark_ai_rs_jp.py --input benchmark_rs_jp_duckdb_20260113_154339.json
  python benchmark_ai_rs_jp.py -i /path/to/benchmark_file.json --model llama2
  python benchmark_ai_rs_jp.py -i benchmark.json -o /custom/output/dir
        """
    )
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Path to the input benchmark JSON file'
    )
    parser.add_argument(
        '-o', '--output-dir',
        default=None,
        help='Output directory for results (default: <project_root>/results)'
    )
    parser.add_argument(
        '-m', '--model',
        default='mistral:latest',
        help='Ollama model to use (default: mistral:latest)'
    )
    parser.add_argument(
        '--ollama-host',
        default='http://0.0.0.0:11434',
        help='Ollama API host (default: http://0.0.0.0:11434)'
    )

    args = parser.parse_args()

    # Configuration
    input_file = args.input

    # Convert relative path to absolute if needed
    input_path = Path(input_file)
    if not input_path.is_absolute():
        input_path = Path.cwd() / input_file
    input_file = str(input_path)

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        # Default to <project_root>/results
        # Assume project root is parent of python-service directory
        project_root = Path(__file__).parent.parent
        output_dir = project_root / "results"

    # Generate output filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Create results directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"ai_evaluation_results_{timestamp}.json"

    # Ollama configuration
    model = args.model
    ollama_host = args.ollama_host

    print("=" * 80)
    print("Benchmark AI RS-JP Evaluation")
    print("=" * 80)
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")
    print(f"Ollama model: {model}")
    print(f"Ollama API: {ollama_host}")
    print("=" * 80)
    print()

    # Load benchmark file
    print(f"Loading benchmark file...")
    try:
        benchmark_data = load_benchmark_file(input_file)
        cases = benchmark_data.get('results', [])
        print(f"Loaded {len(cases)} cases")
        print(
            f"Total cases in benchmark: {benchmark_data.get('total_cases', 'unknown')}")
        print(
            f"Successful cases: {benchmark_data.get('successful_cases', 'unknown')}")
    except Exception as e:
        print(f"Error loading file: {e}")
        return

    # Process all cases
    print(f"\nProcessing cases...")
    all_results = []
    overall_start_time = time.time()

    for i, case in enumerate(cases, 1):
        case_number = case.get('case_number', 'unknown')
        success = case.get('success', False)

        print(
            f"\n[{i}/{len(cases)}] Processing case #{case_number} (success={success})...")

        if not success:
            print(f"  Skipping failed case")
            all_results.append({
                'case_number': case_number,
                'skipped': True,
                'reason': 'Case marked as unsuccessful',
                'total_duration_seconds': 0
            })
            continue

        result = process_case(case, model)
        all_results.append(result)
        print(
            f"  ✓ Completed in {result['total_duration_seconds']:.2f} seconds")
        print(f"    Processed {result['num_r_vals']} r_val(s)")

    overall_duration = time.time() - overall_start_time

    # Create summary
    summary = {
        'benchmark_metadata': {
            'algorithm': benchmark_data.get('algorithm', 'unknown'),
            'database': benchmark_data.get('database', 'unknown'),
            'benchmark_start_time': benchmark_data.get('start_time', 'unknown'),
            'benchmark_total_cases': benchmark_data.get('total_cases', 'unknown'),
            'benchmark_successful_cases': benchmark_data.get('successful_cases', 'unknown')
        },
        'ai_evaluation': {
            'total_cases': len(cases),
            'cases_processed': sum(1 for r in all_results if r.get('case_had_mappings', False)),
            'cases_skipped': sum(1 for r in all_results if r.get('skipped', False)),
            'total_r_vals_processed': sum(r.get('num_r_vals', 0) for r in all_results),
            'total_duration_seconds': overall_duration,
            'model_used': model,
            'timestamp': timestamp,
            'input_file': input_file,
            'output_file': str(output_file)
        }
    }

    # Save results
    print(f"\n{'=' * 80}")
    print(f"Saving results to: {output_file}")
    output_data = {
        'summary': summary,
        'cases': all_results
    }

    with open(output_file, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n{'=' * 80}")
    print("Summary:")
    print(f"  Total cases: {summary['ai_evaluation']['total_cases']}")
    print(f"  Cases processed: {summary['ai_evaluation']['cases_processed']}")
    print(f"  Cases skipped: {summary['ai_evaluation']['cases_skipped']}")
    print(
        f"  Total r_vals processed: {summary['ai_evaluation']['total_r_vals_processed']}")
    print(
        f"  Total duration: {summary['ai_evaluation']['total_duration_seconds']:.2f} seconds")
    print(
        f"  Average time per case: {summary['ai_evaluation']['total_duration_seconds'] / max(summary['ai_evaluation']['cases_processed'], 1):.2f} seconds")
    print(f"\n✓ Done!")
    print("=" * 80)


if __name__ == "__main__":
    main()
