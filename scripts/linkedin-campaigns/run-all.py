#!/usr/bin/env python3
"""Run LinkedIn campaigns sequentially with one campaign assignment per lead."""

import subprocess
import sys


CAMPAIGNS = [
    ("moda-operaciones", ["--industry", "moda", "--role", "operaciones"]),
    ("moda-ceos", ["--industry", "moda", "--role", "ceo"]),
    ("logistica-operaciones", ["--industry", "logistica", "--role", "operaciones"]),
    ("logistica-ceos", ["--industry", "logistica"]),
    ("medianas-integracion", ["--min-employees", "50"]),
]


def main() -> int:
    script_path = "scripts/linkedin-campaigns/send-linkedin.py"
    for index, (template, filters) in enumerate(CAMPAIGNS, start=1):
        print(f"\n{'=' * 70}\n[{index}/{len(CAMPAIGNS)}] {template}\n{'=' * 70}")
        command = [
            sys.executable,
            script_path,
            "--template",
            template,
            "--limit",
            "1000",
            "--yes",
            *filters,
        ]
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            print(f"⚠️ La campaña {template} terminó con código {result.returncode}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
