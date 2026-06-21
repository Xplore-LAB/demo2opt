import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.services.data_loader import ExcelDataLoader
from src.services.data_semantics import DataSemanticsService


def main() -> int:
    parser = argparse.ArgumentParser(description="Build cached history profiles from a source Excel file.")
    parser.add_argument("input_file", help="Path to the source Excel file.")
    parser.add_argument(
        "--output",
        default="tmp/history_profiles.json",
        help="Output JSON cache path. Defaults to tmp/history_profiles.json",
    )
    args = parser.parse_args()

    loader = ExcelDataLoader(args.input_file)
    payload = loader.load_and_standardize()
    records = payload.get("records") or []
    if not records:
        raise ValueError("No standardized records were produced; cannot build history profiles.")

    semantics = DataSemanticsService()
    cache_payload = semantics.write_history_profile_cache(records, output_path=args.output)

    output_path = Path(args.output)
    summary = {
        "output_path": str(output_path),
        "record_count": len(records),
        "tag_count": (cache_payload.get("baseline_profile") or {}).get("tag_count", 0),
        "selected_regime": ((cache_payload.get("baseline_profile") or {}).get("history_model_metadata") or {}).get("selected_regime"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
