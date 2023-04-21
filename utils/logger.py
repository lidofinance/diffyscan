import os


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

    def file_log(self, text):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, mode="a") as logs:
            logs.write(text + "\n")

    def highlight(self, text, color=BOLD):
        return f"{color}{text}{END}"

    def prompt(self, text):
        question = self.highlight("🟡 [PROMPT]", CYAN) + text + " "
        answer = input(question)

        self.file_log("[PROMPT] " + text)
        self.file_log("[ANSWER] " + answer)

        return answer

    def yes_no(self, text):
        question = self.highlight("🟡 [Y/N]", CYAN) + text + " "
        answer = input(question)

        self.file_log("[Y/N] " + text)
        self.file_log("[ANSWER] " + answer)

        return answer.lower() in ["y", "yes"]

    def info(self, text, value=None):
        file_log_text = "🔵 [INFO] " + text
        std_out_text = self.highlight(" 🔵 [INFO] ", BLUE) + text

        if value is not None:
            file_log_text += ": " + str(value)
            std_out_text += ": " + self.highlight(value, BOLD)

        self.file_log(file_log_text)

        print(std_out_text)

    def okay(self, text, value=None):
        file_log_text = "🟢 [OKAY] " + text
        std_out_text = self.highlight(" 🟢 [OKAY] ", GREEN) + text

        if value is not None:
            file_log_text += ": " + str(value)
            std_out_text += ": " + self.highlight(value, BOLD)

        self.file_log(file_log_text)
        print(std_out_text)

    def warn(self, text, value=None):
        file_log_text = "🟠 [WARN] " + text
        std_out_text = self.highlight(" 🟠 [WARN] ", YELLOW) + text

        if value is not None:
            file_log_text += ": " + str(value)
            std_out_text += ": " + self.highlight(value, BOLD)

        self.file_log(file_log_text)
        print(std_out_text)

    def error(self, text, value=None):
        file_log_text = "🔴 [ERROR] " + text
        std_out_text = self.highlight(" 🔴 [ERROR] ", RED) + text

        if value is not None:
            file_log_text += ": " + str(value)
            std_out_text += ": " + self.highlight(value, BOLD)

        self.file_log(file_log_text)
        print(std_out_text)

    def greet(self):
        text = "  🎭  🎭  🎭  🎭\n"
        text += self.highlight("🎭  DiffyScan   🎭\n", GREEN)
        text += "  🎭  🎭  🎭  🎭"
        print(text)

    def divider(
        self,
    ):
        self.file_log(" - +" * 20)
        line = (self.highlight(" -", RED) + self.highlight(" +", GREEN)) * 20
        print("\n" + line + "\n")


logger = Logger("digest/logs.txt")
