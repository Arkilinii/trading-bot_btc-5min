#!/usr/bin/env python3

import html
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request


# =============================================================
# PATHS
# =============================================================

ROOT = Path(__file__).resolve().parents[1]

PAPER_SCRIPT = ROOT / "scripts" / "paper_btc5m.py"
LIVE_SCRIPT = ROOT / "scripts" / "live_btc5m.py"

PAPER_LOG_DIR = ROOT / "logs" / "paper"
LIVE_LOG_DIR = ROOT / "logs" / "live"

PAPER_TRADES_DIR = ROOT / "trades" / "paper"
LIVE_TRADES_DIR = ROOT / "trades" / "live"

# Cross-platform graceful stop request. The bot processes watch this
# file and exit through their normal finally block, so summaries/logs
# are written on both Windows and Linux.
STOP_FILE = ROOT / ".bot_stop"


# =============================================================
# FLASK
# =============================================================

app = Flask(__name__, static_folder="resources", static_url_path="/resources")


# =============================================================
# BOT PROCESS
# =============================================================

bot_process = None
bot_mode = None


# =============================================================
# ANSI -> HTML
# =============================================================

ANSI_RE = re.compile(
    r"\x1b\[([0-9;]*)m"
)


def ansi_to_html(text):

    text = html.escape(text)

    output = []
    pos = 0

    bold = False
    underline = False
    color = None

    def render_segment(segment):

        if not segment:
            return ""

        styles = []

        if color:
            styles.append(
                f"color:{color}"
            )

        if bold:
            styles.append(
                "font-weight:bold"
            )

        if underline:
            styles.append(
                "text-decoration:underline"
            )

        if styles:

            return (
                '<span style="'
                + ";".join(styles)
                + '">'
                + segment
                + "</span>"
            )

        return segment

    for match in ANSI_RE.finditer(text):

        segment = text[
            pos:match.start()
        ]

        output.append(
            render_segment(segment)
        )

        codes = match.group(1)

        if codes == "0" or codes == "":
            bold = False
            underline = False
            color = None

        elif codes == "38;5;208":
            color = "#ff9500"

        else:

            for code in codes.split(";"):

                if code == "1":
                    bold = True

                elif code == "4":
                    underline = True

                elif code == "31":
                    color = "#ff453a"

                elif code == "32":
                    color = "#32d74b"

                elif code == "33":
                    color = "#ffd60a"

                elif code == "34":
                    color = "#0a84ff"

                elif code == "35":
                    color = "#bf5af2"

                elif code == "36":
                    color = "#64d2ff"

                elif code == "37":
                    color = "#ffffff"

                elif code == "39":
                    color = None

        pos = match.end()

    output.append(
        render_segment(
            text[pos:]
        )
    )

    return "".join(output)


# =============================================================
# BOT STATUS
# =============================================================

def is_running():

    global bot_process

    if bot_process is None:
        return False

    if bot_process.poll() is None:
        return True

    bot_process = None

    return False


# =============================================================
# LOG PATHS
# =============================================================

def get_log_paths(mode):

    if mode == "live":

        return (
            LIVE_LOG_DIR,
            LIVE_LOG_DIR / "live.log",
        )

    return (
        PAPER_LOG_DIR,
        PAPER_LOG_DIR / "paper.log",
    )


# =============================================================
# TRADES PATHS
# =============================================================

def get_trade_paths(mode):

    if mode == "live":

        return (
            LIVE_TRADES_DIR,
            LIVE_TRADES_DIR / "live_trades.log",
        )

    return (
        PAPER_TRADES_DIR,
        PAPER_TRADES_DIR / "paper_trades.log",
    )


# =============================================================
# CREATE NOW FILES
# =============================================================

def ensure_now_files(mode):

    log_dir, now_file = get_log_paths(mode)
    trades_dir, trades_file = get_trade_paths(mode)

    log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    trades_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ---------------------------------------------------------
    # IMPORTANTE:
    #
    # Al START se limpia el NOW.
    #
    # Esto permite que el RUN anterior permanezca visible
    # mientras el bot está STOPPED.
    # ---------------------------------------------------------

    now_file.write_text(
        "",
        encoding="utf-8",
    )

    trades_file.write_text(
        "",
        encoding="utf-8",
    )


# =============================================================
# READ CURRENT LOG
# =============================================================

def read_current_log(mode):

    _, now_file = get_log_paths(mode)

    if not now_file.exists():

        return ""

    try:

        return now_file.read_text(
            encoding="utf-8",
            errors="replace",
        )

    except Exception:

        return ""


# =============================================================
# ARCHIVE CURRENT RUN
# =============================================================

def archive_now_log(mode):

    """
    Guarda el RUN actual en el histórico.

    IMPORTANTE:

    El archivo NOW NO se borra aquí.

    Se mantiene para que la interfaz pueda seguir mostrando
    el último RUN cuando el bot está STOPPED.

    El NOW se limpia únicamente en el siguiente START.
    """

    log_dir, now_file = get_log_paths(mode)
    trades_dir, trades_file = get_trade_paths(mode)

    log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    trades_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # =========================================================
    # LEER LOG
    # =========================================================

    if now_file.exists():

        try:

            content = now_file.read_text(
                encoding="utf-8",
                errors="replace",
            )

        except Exception:

            content = ""

    else:

        content = ""

    # =========================================================
    # LEER TRADES
    # =========================================================

    if trades_file.exists():

        try:

            trades_content = trades_file.read_text(
                encoding="utf-8",
                errors="replace",
            )

        except Exception:

            trades_content = ""

    else:

        trades_content = ""

    # =========================================================
    # FECHA
    # =========================================================

    now = datetime.now()

    today = now.strftime(
        "%Y-%m-%d"
    )

    timestamp = now.strftime(
        "%d/%m/%Y %H:%M:%S.%f"
    )[:-3]
    
    
    if mode == "live":

        historical_log = (
            log_dir
            / f"live.log.{today}"
        )

        historical_trades = (
            trades_dir
            / f"live_trades.log.{today}"
        )

    else:

        historical_log = (
            log_dir
            / f"paper.log.{today}"
        )

        historical_trades = (
            trades_dir
            / f"paper_trades.log.{today}"
        )

    # =========================================================
    # ARCHIVAR LOG
    # =========================================================

    if content.strip():

        historical_log_exists = (
            historical_log.exists()
            and historical_log.stat().st_size > 0
        )

        with historical_log.open(
            "a",
            encoding="utf-8",
        ) as f:

            if historical_log_exists:

                f.write("\n")

            else:

                f.write("\n")

            f.write(content)

            if not content.endswith("\n"):

                f.write("\n")

    # =========================================================
    # ARCHIVAR TRADES
    # =========================================================

    if trades_content.strip():

        historical_trades_exists = (
            historical_trades.exists()
            and historical_trades.stat().st_size > 0
        )

        with historical_trades.open(
            "a",
            encoding="utf-8",
        ) as f:

            if historical_trades_exists:

                f.write("\n")

            else:

                f.write(
                    ""
                )
                f.write(
                    "\n"
                    "████████╗██████╗  █████╗ ██████╗ ██╗███╗   ██╗ ██████╗     ██████╗  ██████╗ ████████╗\n"
                    "╚══██╔══╝██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║██╔════╝     ██╔══██╗██╔═══██╗╚══██╔══╝\n"
                    "   ██║   ██████╔╝███████║██║  ██║██║██╔██╗ ██║██║  ███╗    ██████╔╝██║   ██║   ██║   \n"
                    "   ██║   ██╔══██╗██╔══██║██║  ██║██║██║╚██╗██║██║   ██║    ██╔══██╗██║   ██║   ██║   \n"
                    "   ██║   ██║  ██║██║  ██║██████╔╝██║██║ ╚████║╚██████╔╝    ██████╔╝╚██████╔╝   ██║   \n"
                    "   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝╚═╝  ╚═══╝ ╚═════╝     ╚═════╝  ╚═════╝    ╚═╝   \n"
                    "\n"
                    "                              by Arkilinux\n"
                )
                f.write("\n")

            f.write(
                trades_content
            )

            if not trades_content.endswith("\n"):

                f.write("\n")

    # =========================================================
    # NO VACIAR NOW
    # =========================================================
    #
    # DELIBERADAMENTE NO HACEMOS:
    #
    # now_file.write_text("", ...)
    #
    # ni:
    #
    # trades_file.write_text("", ...)
    #
    # El siguiente START será quien los limpie.
    # =========================================================


# =============================================================
# START BOT
# =============================================================

def start_bot(mode):

    global bot_process
    global bot_mode

    if is_running():

        return False

    if mode not in (
        "paper",
        "live",
    ):

        return False

    script = (
        PAPER_SCRIPT
        if mode == "paper"
        else LIVE_SCRIPT
    )

    if not script.exists():

        raise FileNotFoundError(
            f"No existe {script}"
        )

    # =========================================================
    # LIMPIAR NOW AL COMENZAR UN NUEVO RUN
    # =========================================================

    ensure_now_files(
        mode
    )

    # Remove any stale stop request from a previous run.
    try:
        STOP_FILE.unlink(missing_ok=True)
    except OSError:
        pass

    # On Windows the child process must be created as a process group so
    # that we can send CTRL+BREAK to it later. CTRL+C/SIGINT is not a
    # supported signal for Popen.send_signal() on Windows.
    popen_kwargs = {}

    if sys.platform == "win32":

        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP
        )

    bot_process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            str(script),
        ],
        cwd=str(ROOT),
        **popen_kwargs,
    )

    bot_mode = mode

    return True


# =============================================================
# STOP BOT
# =============================================================

def stop_bot():

    global bot_process
    global bot_mode

    if not is_running():

        return False, ""

    stopped_mode = bot_mode

    try:

        # ---------------------------------------------------------
        # GRACEFUL STOP
        #
        # Do not rely on OS signals here. Windows does not support
        # SIGINT through Popen.send_signal() reliably, and CTRL+BREAK
        # can also depend on console/process-group details. Instead,
        # request a graceful shutdown through a small shared file.
        # Both bot scripts check it inside their main loop and leave
        # through their normal finally block.
        # ---------------------------------------------------------
        STOP_FILE.touch(exist_ok=True)

        bot_process.wait(
            timeout=15
        )

    except subprocess.TimeoutExpired:

        # The bot did not shut down gracefully. At this point there
        # is no safe way to guarantee that its asyncio finally block
        # has run, so force the process to stop rather than leaving a
        # zombie/running bot behind.
        bot_process.kill()

        bot_process.wait()

    except (
        ValueError,
        AttributeError,
        OSError,
    ) as exc:

        # Defensive Windows fallback. If CTRL+BREAK is unavailable
        # on a particular Windows environment, stop the process
        # without crashing the Flask /api/stop endpoint.
        if sys.platform == "win32":

            try:
                bot_process.terminate()
                bot_process.wait(
                    timeout=5
                )
            except subprocess.TimeoutExpired:
                bot_process.kill()
                bot_process.wait()
        else:
            raise

    finally:

        bot_process = None
        bot_mode = None

    # =========================================================
    # EL PROCESO YA HA TERMINADO
    #
    # Por tanto, el Trading Summary final ya debería estar
    # escrito en NOW.
    # =========================================================

    final_log = read_current_log(
        stopped_mode
    )

    # The bot process already archived the final NOW files in its
    # finally block. We intentionally do not archive them again here:
    # NOW must remain available to the UI with the final summary.

    return True, final_log


# =============================================================
# HOME
# =============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# =============================================================
# STATUS
# =============================================================

@app.get("/api/status")
def status():

    running = is_running()

    return jsonify(
        {
            "running": running,
            "mode": (
                bot_mode
                if running
                else None
            ),
        }
    )




# =============================================================
# CONNECTION CHECK API
# =============================================================

@app.get("/api/connection-check")
def connection_check():

    script = ROOT / "scripts" / "connection_check.py"

    if not script.exists():

        return jsonify(
            {
                "success": False,
                "error": f"No existe {script}",
            }
        ), 404

    try:

        result = subprocess.run(
            [
                sys.executable,
                "-u",
                str(script),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout or ""

        if result.stderr:
            if output and not output.endswith("\n"):
                output += "\n"
            output += result.stderr

        return jsonify(
            {
                "success": result.returncode == 0,
                "output": output,
                "returncode": result.returncode,
            }
        )

    except subprocess.TimeoutExpired:

        return jsonify(
            {
                "success": False,
                "error": "Connection Check timed out after 30 seconds.",
            }
        ), 504

    except Exception as exc:

        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 500


# =============================================================
# ADDRESS CHECK API
# =============================================================

@app.get("/api/address-check")
def address_check():

    script = ROOT / "scripts" / "address_check.py"

    if not script.exists():

        return jsonify(
            {
                "success": False,
                "error": f"No existe {script}",
            }
        ), 404

    try:

        result = subprocess.run(
            [
                sys.executable,
                "-u",
                str(script),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )

        output = result.stdout or ""

        if result.stderr:
            if output and not output.endswith("\n"):
                output += "\n"
            output += result.stderr

        return jsonify(
            {
                "success": result.returncode == 0,
                "output": output,
                "returncode": result.returncode,
            }
        )

    except subprocess.TimeoutExpired:

        return jsonify(
            {
                "success": False,
                "error": "Address Check timed out after 30 seconds.",
            }
        ), 504

    except Exception as exc:

        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 500


# =============================================================
# START API
# =============================================================

@app.post("/api/start")
def start():

    data = request.get_json(
        silent=True
    ) or {}

    mode = data.get(
        "mode",
        "paper",
    )

    try:

        started = start_bot(
            mode
        )

        return jsonify(
            {
                "success": started,
                "running": is_running(),
                "mode": bot_mode,
            }
        )

    except Exception as exc:

        return jsonify(
            {
                "success": False,
                "error": str(exc),
            }
        ), 500


# =============================================================
# STOP API
# =============================================================

@app.post("/api/stop")
def stop():

    stopped, final_log = stop_bot()

    if not stopped:

        return jsonify(
            {
                "success": False,
                "running": False,
            }
        )

    return jsonify(
        {
            "success": True,
            "running": False,
            "log": ansi_to_html(
                final_log
            ),
        }
    )


# =============================================================
# CURRENT LOG = NOW
# =============================================================

@app.get("/api/log")
def current_log():

    mode = request.args.get(
        "mode",
        "paper",
    )

    _, log_file = get_log_paths(
        mode
    )

    if not log_file.exists():

        return jsonify(
            {
                "log": ""
            }
        )

    try:

        lines = (
            log_file
            .read_text(
                encoding="utf-8",
                errors="replace",
            )
            .splitlines()
        )

        lines = lines[-1000:]

        content = "\n".join(
            lines
        )

        return jsonify(
            {
                "log": ansi_to_html(
                    content
                )
            }
        )

    except Exception as exc:

        return jsonify(
            {
                "log": html.escape(
                    f"Error leyendo log: {exc}"
                )
            }
        )


# =============================================================
# HISTORY DAYS
# =============================================================

@app.get("/api/days")
def days():

    mode = request.args.get(
        "mode",
        "paper",
    )

    log_dir, _ = get_log_paths(
        mode
    )

    log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    prefix = (
        "live.log."
        if mode == "live"
        else "paper.log."
    )

    dates = []

    for file in log_dir.iterdir():

        if not file.is_file():

            continue

        if not file.name.startswith(
            prefix
        ):

            continue

        date = file.name[
            len(prefix):
        ]

        if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            date,
        ):

            dates.append(
                date
            )

    dates.sort(
        reverse=True
    )

    return jsonify(
        {
            "days": dates
        }
    )


# =============================================================
# HISTORY
# =============================================================

@app.get("/api/history")
def history():

    mode = request.args.get(
        "mode",
        "paper",
    )

    date = request.args.get(
        "date",
        "",
    )

    if (
        "/" in date
        or "\\" in date
        or ".." in date
    ):

        return jsonify(
            {
                "log": "Fecha no válida"
            }
        ), 400

    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        date,
    ):

        return jsonify(
            {
                "log": ""
            }
        )

    if mode == "live":

        file = (
            LIVE_LOG_DIR
            / f"live.log.{date}"
        )

    else:

        file = (
            PAPER_LOG_DIR
            / f"paper.log.{date}"
        )

    if not file.exists():

        return jsonify(
            {
                "log": ""
            }
        )

    try:

        content = file.read_text(
            encoding="utf-8",
            errors="replace",
        )

        return jsonify(
            {
                "log": ansi_to_html(
                    content
                )
            }
        )

    except Exception as exc:

        return jsonify(
            {
                "log": html.escape(
                    f"Error leyendo log: {exc}"
                )
            }
        )


# =============================================================
# TRADE DAYS
# =============================================================

@app.get("/api/trade-days")
def trade_days():

    mode = request.args.get(
        "mode",
        "paper",
    )

    trades_dir, _ = get_trade_paths(
        mode
    )

    trades_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    prefix = (
        "live_trades.log."
        if mode == "live"
        else "paper_trades.log."
    )

    dates = []

    for file in trades_dir.iterdir():

        if not file.is_file():

            continue

        if not file.name.startswith(
            prefix
        ):

            continue

        date = file.name[
            len(prefix):
        ]

        if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            date,
        ):

            dates.append(
                date
            )

    dates.sort(
        reverse=True
    )

    return jsonify(
        {
            "days": dates
        }
    )


# =============================================================
# TRADES
# =============================================================

@app.get("/api/trades")
def trades():

    mode = request.args.get(
        "mode",
        "paper",
    )

    date = request.args.get(
        "date",
        "",
    )

    if (
        "/" in date
        or "\\" in date
        or ".." in date
    ):

        return jsonify(
            {
                "log": "Fecha no válida"
            }
        ), 400

    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        date,
    ):

        return jsonify(
            {
                "log": ""
            }
        )

    if mode == "live":

        file = (
            LIVE_TRADES_DIR
            / f"live_trades.log.{date}"
        )

    else:

        file = (
            PAPER_TRADES_DIR
            / f"paper_trades.log.{date}"
        )

    if not file.exists():

        return jsonify(
            {
                "log": ""
            }
        )

    try:

        content = file.read_text(
            encoding="utf-8",
            errors="replace",
        )

        return jsonify(
            {
                "log": ansi_to_html(
                    content
                )
            }
        )

    except Exception as exc:

        return jsonify(
            {
                "log": html.escape(
                    f"Error leyendo trades: {exc}"
                )
            }
        )


# =============================================================
# MAIN
# =============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )