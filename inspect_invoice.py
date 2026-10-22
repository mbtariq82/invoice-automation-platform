
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

ANSWER_PATH = (
    PROJECT_ROOT
    / "invoice-extraction-benchmark"
    / "corpus"
    / "v1"
    / "answers"
    / "clean-us-clean-simple.json"
)

with ANSWER_PATH.open(encoding="utf-8") as file:
    expected = json.load(file)

print(json.dumps(expected, indent=2))
