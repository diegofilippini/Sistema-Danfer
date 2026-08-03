"""Inicializador da versão portátil para Windows."""

from threading import Timer
import os
import webbrowser

import uvicorn


def main() -> None:
    os.environ.setdefault("DANFER_SEED_DEMO", "1")
    os.environ.setdefault("DANFER_SKIP_FIRST_PASSWORD_CHANGE", "1")
    if not os.getenv("DANFER_NO_BROWSER"):
        Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    uvicorn.run(
        "danfer_os.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
