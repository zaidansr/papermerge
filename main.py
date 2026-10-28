"""Desktop entry point; no console window in the packaged Windows build."""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        from papermerge.selftest import run
        raise SystemExit(run(sys.argv[2] if len(sys.argv) > 2 else None))
    from papermerge.gui import main
    main()
