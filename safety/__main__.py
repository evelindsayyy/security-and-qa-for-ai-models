"""``python -m safety merge`` → ``safety.merge`` CLI (same as ``python -m safety.merge``)."""

from safety.merge import main

if __name__ == "__main__":
    raise SystemExit(main())
