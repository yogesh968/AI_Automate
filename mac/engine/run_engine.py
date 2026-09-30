"""PyInstaller entry point (python -m jarvis doesn't work inside a frozen exe)."""

from jarvis.__main__ import main

if __name__ == "__main__":
    main()
