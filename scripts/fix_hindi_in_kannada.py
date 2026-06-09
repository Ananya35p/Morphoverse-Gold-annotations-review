"""Move Hindi poems mislabeled as Kannada into the Hindi folder and update metadata."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output_v3"
KANNADA_DIR = DATA_DIR / "Kannada"
HINDI_DIR = DATA_DIR / "Hindi"

# Devanagari-script poems wrongly filed under Kannada (script-detected + title review).
HINDI_POEM_IDS = [
    "MV++_1042",
    "MV++_1045",
    "MV++_1047",
    "MV++_1048",
    "MV++_1054",
    "MV++_1057",
    "MV++_1059",
    "MV++_1060",
    "MV++_1071",
    "MV++_1072",
    "MV++_1075",
    "MV++_1076",
    "MV++_1078",
    "MV++_1079",
    "MV++_1085",
    "MV++_1092",
    "MV++_1094",
    "MV++_1095",
    "MV++_1096",
]


def update_json_language(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["language"] = "Hindi"
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_csv(path: Path, column: str = "language") -> int:
    if not path.exists():
        return 0
    df = pd.read_csv(path)
    mask = df["poem_id"].isin(HINDI_POEM_IDS)
    count = int(mask.sum())
    if count:
        df.loc[mask, column] = "Hindi"
        df.to_csv(path, index=False)
    return count


def main() -> None:
    HINDI_DIR.mkdir(parents=True, exist_ok=True)
    moved = []
    for poem_id in HINDI_POEM_IDS:
        src = KANNADA_DIR / f"{poem_id}.json"
        dst = HINDI_DIR / f"{poem_id}.json"
        if not src.exists():
            print(f"SKIP (not in Kannada): {poem_id}")
            continue
        if dst.exists():
            print(f"SKIP (already in Hindi): {poem_id}")
            continue
        shutil.move(str(src), str(dst))
        update_json_language(dst)
        moved.append(poem_id)
        print(f"Moved {poem_id} -> Hindi/")

    summary_count = update_csv(DATA_DIR / "annotation_summary.csv")
    queue_count = update_csv(DATA_DIR / "human_review_queue.csv")
    print(f"\nDone. Moved {len(moved)} poems. Updated {summary_count} summary rows, {queue_count} queue rows.")


if __name__ == "__main__":
    main()
