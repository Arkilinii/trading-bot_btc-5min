#!/usr/bin/env python3

import html
import re
import signal
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
LIVE_SCRIPT = ROOT / "script" / "live_btc5m.py"

PAPER_LOG_DIR = ROOT / "logs" / "paper"
LIVE_LOG_DIR = ROOT / "logs" / "live"


# =============================================================
# FLASK
# =============================================================

app = Flask(__name__)


# =============================================================
# BOT PROCESS
# =============================================================

bot_process = None
bot_mode = None


# =============================================================
# ANSI -> HTML
# =============================================================

ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")


def ansi_to_html(text):
    """
    Convierte los colores ANSI utilizados por el bot
    en HTML para que se vean correctamente en el navegador.
    """

    # Escapamos el contenido real del log para que nunca
    # se interprete como HTML.
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
            styles.append(f"color:{color}")

        if bold:
            styles.append("font-weight:bold")

        if underline:
            styles.append("text-decoration:underline")

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

        segment = text[pos:match.start()]
        output.append(render_segment(segment))

        codes = match.group(1)

        # =====================================================
        # RESET
        # =====================================================

        if codes == "0" or codes == "":
            bold = False
            underline = False
            color = None

        # =====================================================
        # ORANGE
        # =====================================================

        elif codes == "38;5;208":
            color = "#ff9500"

        # =====================================================
        # OTHER CODES
        # =====================================================

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

    # Último segmento
    output.append(
        render_segment(text[pos:])
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
# ARCHIVE 
# =============================================================

def archive_now_log(mode):
    """
    Antes de iniciar un nuevo RUN:

    1. Coge lo que haya actualmente en NOW.
    2. Lo añade al histórico del día.
    3. Vacía NOW.

    STOP NO llama a esta función.
    """

    log_dir, now_file = get_log_paths(mode)

    log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Si NOW todavía no existe, lo creamos vacío.
    if not now_file.exists():

        now_file.write_text(
            "",
            encoding="utf-8",
        )

        return

    try:

        content = now_file.read_text(
            encoding="utf-8",
            errors="replace",
        )

    except Exception:

        content = ""

    # Si NOW está vacío, simplemente lo dejamos vacío.
    if not content.strip():

        now_file.write_text(
            "",
            encoding="utf-8",
        )

        return

    # Día actual.
    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    # Histórico correspondiente al día.
    if mode == "live":

        historical_file = (
            log_dir / f"live.log.{today}"
        )

    else:

        historical_file = (
            log_dir / f"paper.log.{today}"
        )

    # Añadimos la sesión anterior al histórico.
    with historical_file.open(
        "a",
        encoding="utf-8",
    ) as f:

        # Si ya había contenido ese día,
        # añadimos un separador entre sesiones.
        if historical_file.stat().st_size > 0:

            f.write("\n")
            f.write("=" * 100)
            f.write("\n")
            f.write(
                "NEW RUN - "
                + datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
            f.write("\n")
            f.write("=" * 100)
            f.write("\n")

        f.write(content)

        if not content.endswith("\n"):
            f.write("\n")

    # =========================================================
    # AHORA VACÍAMOS NOW
    # =========================================================

    now_file.write_text(
        "",
        encoding="utf-8",
    )


# =============================================================
# START BOT
# =============================================================

def start_bot(mode):

    global bot_process
    global bot_mode

    if is_running():
        return False

    if mode not in ("paper", "live"):
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
    # ANTES DE CADA RUN
    #
    # Lo que había en NOW pasa al histórico del día.
    # Después NOW queda vacío.
    # =========================================================

    archive_now_log(mode)

    # =========================================================
    # ARRANCAR BOT
    # =========================================================

    bot_process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            str(script),
        ],
        cwd=str(ROOT),
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
        return False

    try:

        bot_process.send_signal(
            signal.SIGINT
        )

        bot_process.wait(
            timeout=10
        )

    except subprocess.TimeoutExpired:

        bot_process.kill()

        bot_process.wait()

    finally:

        # IMPORTANTE:
        #
        # STOP NO ARCHIVA NI BORRA NOW.
        # El contenido permanece tal cual.
        #

        bot_process = None
        bot_mode = None

    return True


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
# START
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
# STOP
# =============================================================

@app.post("/api/stop")
def stop():

    stopped = stop_bot()

    return jsonify(
        {
            "success": stopped,
            "running": is_running(),
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

        lines = log_file.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()

        # Últimas 1000 líneas.
        lines = lines[-1000:]

        content = "\n".join(lines)

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
# DAYS
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

    for file in log_dir.glob(
        prefix + "*"
    ):

        date = file.name.replace(
            prefix,
            "",
        )

        # Solo aceptamos fechas reales
        # con formato YYYY-MM-DD.
        if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            date,
        ):

            dates.append(date)

    dates.sort(
        reverse=True
    )

    # NOW siempre aparece primero.
    dates.insert(
        0,
        "NOW",
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

    # =========================================================
    # SEGURIDAD
    # =========================================================

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

    # =========================================================
    # NOW
    # =========================================================

    if date == "NOW":

        _, file = get_log_paths(
            mode
        )

    # =========================================================
    # HISTÓRICO
    # =========================================================

    else:

        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            date,
        ):

            return jsonify(
                {
                    "log": "Fecha no válida"
                }
            ), 400

        if mode == "live":

            log_dir = LIVE_LOG_DIR

            file = (
                log_dir
                / f"live.log.{date}"
            )

        else:

            log_dir = PAPER_LOG_DIR

            file = (
                log_dir
                / f"paper.log.{date}"
            )

    # =========================================================
    # FILE NOT FOUND
    # =========================================================

    if not file.exists():

        return jsonify(
            {
                "log": ""
            }
        )

    # =========================================================
    # READ
    # =========================================================

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
# MAIN
# =============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
    )
