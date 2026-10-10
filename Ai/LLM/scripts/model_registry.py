"""Inspect inventory, or explicitly select a reviewed model; no deletion command."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.model_registry import read_registry, select, cleanup_inventory

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--select')
    parser.add_argument('--cleanup-inventory', action='store_true')
    args = parser.parse_args()
    value = select(args.select) if args.select else cleanup_inventory() if args.cleanup_inventory else read_registry()
    print(json.dumps(value, ensure_ascii=False, indent=2))
