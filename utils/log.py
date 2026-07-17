from __future__ import annotations

from datetime import datetime
import sys

try:
    from colorama import Fore, Style, init  # pyright: ignore[reportMissingModuleSource]

    init(autoreset=True)
    COLORS = {
        "red": Fore.RED,
        "green": Fore.GREEN,
        "yellow": Fore.YELLOW,
        "blue": Fore.BLUE,
        "cyan": Fore.CYAN,
        "magenta": Fore.MAGENTA,
        "white": Fore.WHITE,
    }
    RESET = Style.RESET_ALL
except Exception:
    COLORS = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "cyan": "\033[96m",
        "magenta": "\033[95m",
        "white": "\033[97m",
    }
    RESET = "\033[0m"


def _safe_text(value: object) -> str:
    text = str(value)
    encoding = sys.stdout.encoding or "utf-8"
    try:
        return text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    except Exception:
        return text.encode("ascii", errors="replace").decode("ascii", errors="replace")


def log(msg: object, color: str | None = None) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    text = _safe_text(msg)
    prefix = f"[{ts}] "
    shade = COLORS.get((color or "").lower())
    if shade:
        try:
            print(f"{prefix}{shade}{text}{RESET}")
            return
        except Exception:
            pass
    print(f"{prefix}{text}")
