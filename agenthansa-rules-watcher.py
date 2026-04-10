#!/usr/bin/env python3
import json

from agenthansa_runtime_profile import fetch_rules_summary


def main():
    print(json.dumps(fetch_rules_summary(), ensure_ascii=False))


if __name__ == '__main__':
    main()
