import os
import sys
import json
from pathlib import Path
from collections import Counter

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.llm.qwen_client import generate_text_to_sql_qwen
from app.db.sql_executor import execute_sql_query


def _get_case_insensitive_val(row_dict: dict, col_name: str):
    """Performs case-insensitive key lookup in a row dictionary."""
    if not isinstance(row_dict, dict):
        return None
    for k, v in row_dict.items():
        if k.lower() == col_name.lower():
            return v
    return None


def evaluate_semantic_match(expected_rows: list, generated_rows: list, eval_config: dict) -> dict:
    """
    Evaluates semantic result correctness based on underlying expected values and row counts.
    Column alias differences do NOT fail semantic_result_match.
    Computes alias_match separately to track exact column alias naming.
    """
    key_cols = eval_config.get("key_columns", [])
    val_cols = eval_config.get("value_columns", [])
    required_cols = key_cols + val_cols
    expected_row_count = eval_config.get("expected_row_count")
    order_by = eval_config.get("order_by", [])

    actual_row_count = len(generated_rows)
    target_count = expected_row_count if expected_row_count is not None else len(expected_rows)
    row_count_match = (actual_row_count == target_count)

    if not generated_rows and target_count > 0:
        return {
            "semantic_result_match": False,
            "alias_match": False,
            "required_columns_match": False,
            "row_count_match": False,
            "ordering_match": False if order_by else True,
            "extra_columns": [],
            "missing_required_columns": required_cols
        }

    gen_sample = generated_rows[0] if generated_rows else {}
    exp_sample = expected_rows[0] if expected_rows else {}

    gen_keys = [k.lower() for k in gen_sample.keys()] if isinstance(gen_sample, dict) else []
    exp_keys = [k.lower() for k in exp_sample.keys()] if isinstance(exp_sample, dict) else []

    # Check alias match separately
    alias_match = (gen_keys == exp_keys)

    # Check missing required columns by name or positional value availability
    missing_cols = []
    gen_keys_lower = set(gen_keys)
    for req_col in required_cols:
        if req_col.lower() not in gen_keys_lower:
            # Fallback: if positional value exists in row, count as present
            if not (len(gen_sample) >= len(required_cols)):
                missing_cols.append(req_col)

    required_columns_match = (len(missing_cols) == 0)

    req_cols_lower = {c.lower() for c in required_cols}
    extra_cols = (
        [k for k in gen_sample.keys() if k.lower() not in req_cols_lower]
        if isinstance(gen_sample, dict) else []
    )

    # Extract required column values by case-insensitive name or position
    def extract_semantic_tuple(row, is_generated=False):
        if not required_cols:
            return tuple(row.values()) if isinstance(row, dict) else tuple(row)
        vals = []
        gen_row_keys = list(row.keys()) if isinstance(row, dict) else []
        for idx, c in enumerate(required_cols):
            if isinstance(row, dict):
                v = _get_case_insensitive_val(row, c)
                # Positional fallback if column alias differs
                if v is None and idx < len(gen_row_keys):
                    v = list(row.values())[idx]
                vals.append(v)
            else:
                vals.append(row)
        return tuple(vals)

    gen_tuples = [extract_semantic_tuple(r, is_generated=True) for r in generated_rows]
    exp_tuples = [extract_semantic_tuple(r) for r in expected_rows]

    ordering_match = True
    if order_by:
        ordering_match = (gen_tuples == exp_tuples)
        semantic_match = row_count_match and required_columns_match and ordering_match
    else:
        multiset_match = (Counter(gen_tuples) == Counter(exp_tuples))
        semantic_match = row_count_match and required_columns_match and multiset_match

    return {
        "semantic_result_match": semantic_match,
        "alias_match": alias_match,
        "required_columns_match": required_columns_match,
        "row_count_match": row_count_match,
        "ordering_match": ordering_match,
        "extra_columns": extra_cols,
        "missing_required_columns": missing_cols
    }


def main():
    test_dir = Path(__file__).resolve().parent
    dataset_file = test_dir / "data" / "sales_order_header_tests.json"
    results_dir = test_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    if not dataset_file.exists():
        print(f"Error: Dataset file '{dataset_file}' not found.")
        sys.exit(1)

    with open(dataset_file, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    print(f"Starting Qwen Semantic Text-to-SQL evaluation on {len(test_cases)} test cases...\n")

    results = []
    semantic_correct_count = 0
    execution_success_count = 0
    exact_sql_match_count = 0
    alias_match_count = 0

    for idx, tc in enumerate(test_cases, 1):
        test_id = tc.get("id")
        category = tc.get("category")
        question = tc.get("question")
        expected_sql = tc.get("expected_sql")
        eval_config = tc.get("evaluation", {})

        print(f"[{idx}/{len(test_cases)}] Running {test_id} ({category}): '{question}'")

        # 1. Generate SQL using Qwen client
        try:
            generated_sql = generate_text_to_sql_qwen(question)
        except Exception as e:
            print(f"  -> Qwen generation error: {e}")
            generated_sql = None

        # 2. Execute generated SQL
        generated_result = []
        execution_success = False
        if generated_sql and (generated_sql.strip().upper().startswith("SELECT") or generated_sql.strip().upper().startswith("WITH")):
            try:
                generated_result = execute_sql_query(generated_sql)
                execution_success = True
            except Exception as e:
                print(f"  -> Generated SQL execution error: {e}")
                execution_success = False
                generated_result = []

        # 3. Execute expected SQL
        expected_result = []
        try:
            expected_result = execute_sql_query(expected_sql)
        except Exception as e:
            print(f"  -> Expected SQL execution error: {e}")
            expected_result = []

        # 4. Perform Positional/Semantic Evaluation
        eval_result = evaluate_semantic_match(expected_result, generated_result, eval_config)
        
        # Override semantic_result_match if execution failed
        semantic_result_match = eval_result["semantic_result_match"] and execution_success
        alias_match = eval_result["alias_match"]

        # Exact SQL match check (informational metric)
        sql_exact_match = False
        if generated_sql and expected_sql:
            norm_gen = generated_sql.strip().rstrip(";").lower()
            norm_exp = expected_sql.strip().rstrip(";").lower()
            sql_exact_match = (norm_gen == norm_exp)

        if execution_success:
            execution_success_count += 1
        if semantic_result_match:
            semantic_correct_count += 1
        if alias_match:
            alias_match_count += 1
        if sql_exact_match:
            exact_sql_match_count += 1

        print(f"  -> Execution Success: {execution_success} | Semantic Match: {semantic_result_match} | Alias Match: {alias_match} | Exact SQL: {sql_exact_match}\n")

        results.append({
            "id": test_id,
            "category": category,
            "question": question,
            "expected_sql": expected_sql,
            "generated_sql": generated_sql,
            "execution_success": execution_success,
            "semantic_result_match": semantic_result_match,
            "alias_match": alias_match,
            "sql_exact_match": sql_exact_match,
            "required_columns_match": eval_result["required_columns_match"],
            "row_count_match": eval_result["row_count_match"],
            "ordering_match": eval_result["ordering_match"],
            "extra_columns": eval_result["extra_columns"],
            "missing_required_columns": eval_result["missing_required_columns"],
            "expected_result": expected_result,
            "generated_result": generated_result
        })

    # Save detailed evaluation results to JSON file
    output_results_file = results_dir / "qwen_sales_order_header_results.json"
    with open(output_results_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Print summary
    total = len(test_cases)
    print("=" * 40)
    print(f"Total: {total}")
    print(f"Semantic correct: {semantic_correct_count}/{total}")
    print(f"Alias match: {alias_match_count}/{total}")
    print(f"Execution success: {execution_success_count}/{total}")
    print(f"Exact SQL match: {exact_sql_match_count}/{total}")
    print("=" * 40)
    print(f"Detailed results saved to '{output_results_file.resolve()}'")


if __name__ == "__main__":
    main()
