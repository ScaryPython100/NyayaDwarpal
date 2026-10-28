import sys
from pathlib import Path

# Shared Lambda-layer modules import each other by bare name (as they do from /opt/python)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lambda_functions" / "shared"))
