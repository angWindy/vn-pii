"""Enable ``python -m pii_linter`` as a mirror of the ``pa1-lint`` script.

Kept to a re-export of :func:`pii_linter.cli.main` so both entry points
share one code path (and one exit-code convention) with no drift.
"""

from pii_linter.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
