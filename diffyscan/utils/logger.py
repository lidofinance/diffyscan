import termtables

from .constants import LOGS_PATH
from .helpers import create_dirs

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


class Logger:
    def __init__(self, log_file):
        self.log_file = log_file

    # log to file
    def log(self, text):
        create_dirs(self.log_file)
        with open(self.log_file, mode="a") as logs:
            logs.write(text + "\n")

    # print to std out
    def stdout(self, text, overwrite=False):
        end_char = "\r" if overwrite else "\n"
        print(text, end=end_char, flush=overwrite)

    def info(self, text, value=None):
        log_text = "🔵 [INFO] " + text
        stdout_text = self.hl(" 🔵 [INFO] ", BLUE) + text

        if value is not None:
            log_text = self.cln(log_text, value)
            stdout_text = self.cln(stdout_text, self.hl(value, BOLD))

        self.log(log_text)
        self.stdout(stdout_text)

    def update_info(self, text, value=None):
        log_text = "🔵 [INFO] " + text
        stdout_text = self.hl(" 🔵 [INFO] ", BLUE) + text

        if value is not None:
            log_text = self.cln(log_text, value)
            stdout_text = self.cln(stdout_text, self.hl(value, BOLD))

        self.log(log_text)
        self.stdout(stdout_text + (" " * 100), overwrite=True)

    def okay(self, text, value=None):
        log_text = "🟢 [OKAY] " + text
        stdout_text = self.hl(" 🟢 [OKAY] ", GREEN) + text

        if value is not None:
            log_text += ": " + str(value)
            stdout_text += ": " + self.hl(value, BOLD)

        self.log(log_text)
        self.stdout(stdout_text)

    def warn(self, text, value=None):
        log_text = "🟠 [WARN] " + text
        stdout_text = self.hl(" 🟠 [WARN] ", YELLOW) + text

        if value is not None:
            log_text += ": " + str(value)
            stdout_text += ": " + self.hl(value, BOLD)

        self.log(log_text)
        self.stdout(stdout_text)

    def error(self, text, value=None):
        log_text = "🔴 [ERROR] " + text
        stdout_text = self.hl(" 🔴 [ERROR] ", RED) + text

        if value is not None:
            log_text += ": " + str(value)
            stdout_text += ": " + self.hl(value, BOLD)

        self.log(log_text)
        self.stdout(stdout_text)

    def report_table(self, table):
        log_table = termtables.to_string(
            table,
            header=["#", "Filename", "Found", "Diffs", "Origin", "Report"],
            style=termtables.styles.rounded_double,
        )
        self.log(log_table)

        stdout_table = [self.color_row(row) for row in table]
        table_colored_string = termtables.to_string(
            stdout_table,
            header=["#", "Filename", "Found", "Diffs", "Origin", "Report"],
            style=termtables.styles.rounded_double,
        )

        self.stdout(table_colored_string)

    def color_row(self, row):
        hlcolor = GREEN

        file_found = row[2]
        diffs_found = row[3] is not None and row[3] > 0

        if not file_found:
            hlcolor = RED
        elif diffs_found:
            hlcolor = RED

        return [self.hl(cell, hlcolor) for cell in row]

    def hl(self, text, color=BOLD):
        return f"{color}{text}{END}"

    def hlgreen(self, text):
        return self.hl(text, GREEN)

    def hlblue(self, text):
        return self.hl(text, BLUE)

    def hlred(self, text):
        return self.hl(text, RED)

    def cln(self, text1, text2):
        return f"{text1}: {text2}"

    def divider(self):
        self.log(" - +" * 20)
        self.stdout((self.hlred(" -") + self.hlgreen(" +")) * 20)


logger = Logger(LOGS_PATH)


def to_hex(index, padStart=2):
    return f"{index:0{padStart}X}"


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
