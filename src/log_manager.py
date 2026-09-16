import logging
from datetime import datetime
from pathlib import Path


def _historical_path(
    current_file: Path,
    date: str,
) -> Path:
    return current_file.parent / f"{current_file.name}.{date}"


def _flush_handlers(
    current_file: Path,
) -> None:
    target = str(current_file.resolve())

    for handler in logging.getLogger().handlers:
        if not isinstance(handler, logging.FileHandler):
            continue

        if str(Path(handler.baseFilename).resolve()) != target:
            continue

        handler.flush()


def _clear_current_file(
    current_file: Path,
) -> None:
    target = str(current_file.resolve())

    for handler in logging.getLogger().handlers:
        if not isinstance(handler, logging.FileHandler):
            continue

        if str(Path(handler.baseFilename).resolve()) != target:
            continue

        handler.flush()

        if handler.stream is not None:
            handler.stream.seek(0)
            handler.stream.truncate(0)
            handler.stream.flush()
            return

    current_file.write_text("", encoding="utf-8")


TRADE_HEADER = (
    "\n"
    "████████╗██████╗  █████╗ ██████╗ ██╗███╗   ██╗ ██████╗     ██████╗  ██████╗ ████████╗\n"
    "╚══██╔══╝██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║██╔════╝     ██╔══██╗██╔═══██╗╚══██╔══╝\n"
    "   ██║   ██████╔╝███████║██║  ██║██║██╔██╗ ██║██║  ███╗    ██████╔╝██║   ██║   ██║   \n"
    "   ██║   ██╔══██╗██╔══██║██║  ██║██║██║╚██╗██║██║   ██║    ██╔══██╗██║   ██║   ██║   \n"
    "   ██║   ██║  ██║██║  ██║██████╔╝██║██║ ╚████║╚██████╔╝    ██████╔╝╚██████╔╝   ██║   \n"
    "   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝╚═╝  ╚═══╝ ╚═════╝     ╚═════╝  ╚═════╝    ╚═╝   \n"
    "\n"
    "                              by Arkilinux\n"
    "\n"
)


def archive_log_file(
    current_file: Path,
    clear: bool = True,
    header: str = "",
) -> None:
    """
    Append the current NOW log to today's History file.

    If clear=True, NOW is emptied after the copy so the next
    logging block starts from an empty file.
    """
    current_file = Path(current_file)

    if not current_file.exists():
        return

    _flush_handlers(current_file)

    content = current_file.read_text(
        encoding="utf-8",
        errors="replace",
    )

    if not content.strip():
        return

    today = datetime.now().strftime("%Y-%m-%d")
    historical_file = _historical_path(
        current_file,
        today,
    )

    historical_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    historical_exists = (
        historical_file.exists()
        and historical_file.stat().st_size > 0
    )

    with historical_file.open("a", encoding="utf-8") as f:
        if historical_exists:
            f.write("\n")
        elif header:
            f.write(header)
        f.write(content)
        if not content.endswith("\n"):
            f.write("\n")

    if clear:
        _clear_current_file(current_file)


def archive_logs(
    log_file: Path,
    trades_file: Path,
) -> None:
    """Archive both normal and trade NOW files to today's History."""
    archive_log_file(log_file, clear=True)
    archive_log_file(trades_file, clear=True)
