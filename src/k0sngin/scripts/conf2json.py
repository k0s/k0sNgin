"""
Convert a conf-file to JSON
"""

import argparse
import json
import sys
from k0sngin.parser import parse_config


def main():
    """CLI entry point"""
    # Parse arguments
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', type=argparse.FileType('r'), default=sys.stdin, help='The input conf-file')
    options = parser.parse_args()

    # Read and parse configuration
    content = options.input.read()
    config = parse_config(content)

    # Print JSON
    print(json.dumps(config, indent=4))


if __name__ == '__main__':
    main()