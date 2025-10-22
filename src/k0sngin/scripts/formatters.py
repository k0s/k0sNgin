"""
List available formatters
"""

import sys
from k0sngin.formatter import formatters

def main(args=sys.argv[1:]):
    """CLI entry point"""

    for name, formatter in formatters.items():
        print(f"{name}: {formatter.__doc__}")

if __name__ == "__main__":
    sys.exit(main() or 0)
