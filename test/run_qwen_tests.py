"""Run the SalesOrderHeader Text-to-SQL semantic benchmark against the active path.

This is an opt-in integration benchmark. It uses the same retrieval, structured
generation, SQL validation, and safe executor used by the application, so it
requires configured Ollama, Qdrant, and SQL Server services.
"""

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.db.sql_executor import execute_sql_query, execute_validated_sql
from app.db.sql_validator import validate_sql
from app.retrieval.context_builder import build_text_to_sql_context
from app.sales.text_to_sql import TextToSQLGenerator


DEFAULT_DATASET = Path("test/data/sales_order_header_tests.json")
DEFAULT_OUTPUT = Path("test/results/qwen_sales_order_header_results.json")


def _get_case_insensitive_val(row_dict: dict[str, Any], col_name: str) -> Any:
    """Perform a case-insensitive key lookup in one result row."""
    for key, value in row_dict.items():
        if key.lower() == col_name.lower():
            return value
    return None


def evaluate_semantic_match(expected_rows: list[dict[str, Any]], generated_rows: list[dict[str, Any]], eval_config: dict[str, Any]) -> dict[str, Any]:
    """Compare expected and generated results while tolerating output aliases."""
    key_cols = eval_config.get("key_columns", [])
    value_cols = eval_config.get("value_columns", [])
    required_cols = key_cols + value_cols
    expected_row_count = eval_config.get("expected_row_count")
    order_by = eval_config.get("order_by", [])
    target_count = expected_row_count if expected_row_count is not None else len(expected_rows)
    row_count_match = len(generated_rows) == target_count

    if not generated_rows and target_count > 0:
        return {
            "semantic_result_match": False,
            "alias_match": False,
            "required_columns_match": False,
            "row_count_match": False,
            "ordering_match": not order_by,
            "extra_columns": [],
            "missing_required_columns": required_cols,
        }

    generated_sample = generated_rows[0] if generated_rows else {}
    expected_sample = expected_rows[0] if expected_rows else {}
    generated_keys = [key.lower() for key in generated_sample]
    expected_keys = [key.lower() for key in expected_sample]
    alias_match = generated_keys == expected_keys
    missing_columns = [
        column for column in required_cols
        if column.lower() not in generated_keys and len(generated_sample) < len(required_cols)
    ]
    required_columns_match = not missing_columns
    required_lower = {column.lower() for column in required_cols}
    extra_columns = [key for key in generated_sample if key.lower() not in required_lower]

    def semantic_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
        if not required_cols:
            return tuple(row.values())
        values = []
        positional_values = list(row.values())
        for index, column in enumerate(required_cols):
            value = _get_case_insensitive_val(row, column)
            values.append(positional_values[index] if value is None and index < len(positional_values) else value)
        return tuple(values)

    generated_tuples = [semantic_tuple(row) for row in generated_rows]
    expected_tuples = [semantic_tuple(row) for row in expected_rows]
    ordering_match = generated_tuples == expected_tuples if order_by else True
    values_match = ordering_match if order_by else Counter(generated_tuples) == Counter(expected_tuples)
    return {
        "semantic_result_match": row_count_match and required_columns_match and values_match,
        "alias_match": alias_match,
        "required_columns_match": required_columns_match,
        "row_count_match": row_count_match,
        "ordering_match": ordering_match,
        "extra_columns": extra_columns,
        "missing_required_columns": missing_columns,
    }


async def run_benchmark(dataset_file: Path, output_file: Path, max_cases: int | None = None) -> int:
    """Run selected cases and return zero only when all generated SQL executes."""
    if not dataset_file.exists():
        raise FileNotFoundError(f"Dataset file '{dataset_file}' was not found.")
    test_cases = json.loads(dataset_file.read_text(encoding="utf-8"))
    if max_cases is not None:
        test_cases = test_cases[:max_cases]

    print(f"Starting active Text-to-SQL semantic evaluation on {len(test_cases)} test cases...\n")
    generator = TextToSQLGenerator()
    results: list[dict[str, Any]] = []
    counts = Counter()

    for index, test_case in enumerate(test_cases, 1):
        question = test_case["question"]
        expected_sql = test_case["expected_sql"]
        print(f"[{index}/{len(test_cases)}] {test_case['id']} ({test_case['category']}): {question!r}")

        generated_sql: str | None = None
        generated_rows: list[dict[str, Any]] = []
        generation_error: str | None = None
        validation_errors: list[str] = []
        execution_success = False
        try:
            context = await build_text_to_sql_context(question)
            generated_sql = (await generator.generate_sql(question, context)).sql
        except Exception as exc:
            generation_error = str(exc)
            print(f"  -> Generation error: {generation_error}")

        if generated_sql:
            validation = validate_sql(generated_sql)
            validation_errors = validation.errors
            if validation.valid:
                try:
                    generated_rows = execute_validated_sql(validation)
                    execution_success = True
                except Exception as exc:
                    generation_error = str(exc)
                    print(f"  -> Generated SQL execution error: {generation_error}")
            else:
                print(f"  -> Generated SQL validation error: {'; '.join(validation_errors)}")

        try:
            expected_rows = execute_sql_query(expected_sql)
        except Exception as exc:
            expected_rows = []
            generation_error = generation_error or f"Expected SQL execution error: {exc}"
            print(f"  -> Expected SQL execution error: {exc}")

        evaluation = evaluate_semantic_match(expected_rows, generated_rows, test_case.get("evaluation", {}))
        semantic_match = execution_success and evaluation["semantic_result_match"]
        exact_sql_match = bool(generated_sql) and generated_sql.strip().rstrip(";").lower() == expected_sql.strip().rstrip(";").lower()
        counts.update(
            execution_success=execution_success,
            semantic_match=semantic_match,
            alias_match=evaluation["alias_match"],
            exact_sql_match=exact_sql_match,
        )
        print(f"  -> Executed: {execution_success} | Semantic: {semantic_match} | Aliases: {evaluation['alias_match']} | Exact SQL: {exact_sql_match}\n")
        results.append({
            "id": test_case["id"],
            "category": test_case["category"],
            "question": question,
            "expected_sql": expected_sql,
            "generated_sql": generated_sql,
            "generation_error": generation_error,
            "validation_errors": validation_errors,
            "execution_success": execution_success,
            "semantic_result_match": semantic_match,
            "alias_match": evaluation["alias_match"],
            "sql_exact_match": exact_sql_match,
            **evaluation,
            "expected_result": expected_rows,
            "generated_result": generated_rows,
        })

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    total = len(test_cases)
    print("=" * 40)
    print(f"Total: {total}")
    print(f"Semantic correct: {counts['semantic_match']}/{total}")
    print(f"Alias match: {counts['alias_match']}/{total}")
    print(f"Execution success: {counts['execution_success']}/{total}")
    print(f"Exact SQL match: {counts['exact_sql_match']}/{total}")
    print("=" * 40)
    print(f"Detailed results saved to '{output_file.resolve()}'")
    return 0 if counts["execution_success"] == total else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-cases", type=int, help="Run only the first N cases for a smoke benchmark.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(asyncio.run(run_benchmark(args.dataset, args.output, args.max_cases)))


if __name__ == "__main__":
    main()
