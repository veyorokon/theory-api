"""Command line argument parsing for processors."""
import argparse


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse standard processor arguments."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True, help="Path to inputs.json")
    ap.add_argument("--write-prefix", required=True, help="World write prefix (not used inside container)")
    return ap.parse_args(argv)