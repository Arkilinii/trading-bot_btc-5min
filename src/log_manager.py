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


# For clear=False archives, remember how much of each NOW file has already
# been copied to History during the current bot process.  This lets NOW
# remain intact while History receives only the newly generated log lines.
_archived_lengths = {}


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
    Append NOW to today's History.

    When clear=True, the whole current file is archived and NOW is emptied.
    When clear=False, NOW is preserved and only the portion generated since
    the previous clear=False archive call in this process is appended.
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

    key = str(current_file.resolve())
    previous_length = _archived_lengths.get(key, 0)

    # If NOW was externally truncated/recreated, restart from the beginning
    # instead of slicing beyond the current content.
    if previous_length > len(content):
        previous_length = 0

    if clear:
        content_to_archive = content
    else:
        content_to_archive = content[previous_length:]

    if not content_to_archive.strip():
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
        f.write(content_to_archive)
        if not content_to_archive.endswith("\n"):
            f.write("\n")

    if clear:
        _clear_current_file(current_file)
        _archived_lengths[key] = 0
    else:
        _archived_lengths[key] = len(content)


def archive_logs(
    log_file: Path,
    trades_file: Path,
) -> None:
    """Archive both normal and trade NOW files to today's History."""
    archive_log_file(log_file, clear=True)
    archive_log_file(trades_file, clear=True)
