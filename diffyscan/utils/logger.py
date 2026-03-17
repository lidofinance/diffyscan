from pathlib import Path

import termtables

from .constants import LOGS_PATH

CYAN = "\033[96m"
PURPLE = "\033[95m"
DARKCYAN = "\033[36m"
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"

BOLD = "\033[1m"
UNDERLINE = "\033[4m"

END = "\033[0m"


_LOG_LEVELS = {
    "info": (0, "🔵 [INFO] ", BLUE),
    "okay": (1, "🟢 [OKAY] ", GREEN),
    "warn": (2, "🟠 [WARN] ", YELLOW),
    "error": (3, "🔴 [ERROR] ", RED),
}


class Logger:
    def __init__(self, log_file):
        self.log_file = log_file
        self.level = 0

    def set_level(self, level_name: str):
        self.level = _LOG_LEVELS.get(level_name.lower(), (0,))[0]

    def log(self, text):
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, mode="a") as logs:
            logs.write(text + "\n")

    def stdout(self, text, overwrite=False):
        end_char = "\r" if overwrite else "\n"
        print(text, end=end_char, flush=overwrite)

    def _emit(self, level_name, text, value=None, overwrite=False):
        threshold, emoji, color = _LOG_LEVELS[level_name]
        log_text = emoji + text
        stdout_text = f"{color} {emoji}{END}{text}"

        if value is not None:
            log_text += f": {value}"
            stdout_text += f": {BOLD}{value}{END}"

        self.log(log_text)
        if self.level <= threshold:
            if overwrite:
                stdout_text += " " * 100
            self.stdout(stdout_text, overwrite=overwrite)

    def info(self, text, value=None):
        self._emit("info", text, value)

    def update_info(self, text, value=None):
        self._emit("info", text, value, overwrite=True)

    def okay(self, text, value=None):
        self._emit("okay", text, value)

    def warn(self, text, value=None):
        self._emit("warn", text, value)

    def error(self, text, value=None):
        self._emit("error", text, value)

    def report_table(self, table):
        header = ["#", "Filename", "Found", "Diffs", "Origin", "Report"]
        self.log(
            termtables.to_string(
                table,
                header=header,
                style=termtables.styles.rounded_double,
            )
        )
        colored = [self._color_row(row) for row in table]
        self.stdout(
            termtables.to_string(
                colored,
                header=header,
                style=termtables.styles.rounded_double,
            )
        )

    def _color_row(self, row):
        color = RED if (not row[2] or (row[3] is not None and row[3] > 0)) else GREEN
        return [f"{color}{cell}{END}" for cell in row]

    def divider(self):
        self.log(" - +" * 20)
        if self.level <= 0:
            self.stdout((f"{RED} -{END}{GREEN} +{END}") * 20)


logger = Logger(LOGS_PATH)


def to_hex(index, pad=2):
    return f"{index:0{pad}X}"


def red(text):
    return f"\u001b[31m{text}\x1b[0m"


def bgRed(text):
    return f"\u001b[37;41m{text}\x1b[0m"


def green(text):
    return f"\u001b[32m{text}\x1b[0m"


def bgGreen(text):
    return f"\u001b[37;42m{text}\x1b[0m"


def bgYellow(text):
    return f"\u001b[37;43m{text}\x1b[0m"
