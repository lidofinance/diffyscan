CYAN = '\033[96m'
PURPLE = '\033[95m'
DARKCYAN = '\033[36m'
BLUE = '\033[94m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'

BOLD = '\033[1m'
UNDERLINE = '\033[4m'

END = '\033[0m'


def highlight(text, color=BOLD):
    return f"{color}{text}{END}"


def prompt(text):
    question = highlight(" ❔ [PROMPT]: ", CYAN) + text + " "
    answer = input(question)
    return answer

def yes_no(text):
    question = highlight(" ❔ [YES/NO]: ", CYAN) + text + " "
    answer = input(question)
    return answer.lower() in ["y", "yes"]


def info(text, value=None):
    result = highlight(" 🔵 [INFO] ", BLUE) + text

    if value is not None:
        result += ": " + highlight(value, BOLD)

    print(result)


def okay(text, value=None):
    result = highlight(" 🟢 [OKAY] ", GREEN) + text

    if value is not None:
        result += ": " + highlight(value, BOLD)

    print(result)


def warn(text, value=None):
    result = highlight(" 🟠 [WARN] ", YELLOW) + text

    if value is not None:
        result += ": " + highlight(value, BOLD)

    print(result)


def error(text, value=None):
    result = highlight(" 🔴 [ERROR] ", RED) + text

    if value is not None:
        result += ": " + highlight(value, BOLD)

    print(result)


def greet():
    text = "  🎭  🎭  🎭  🎭\n"
    text += highlight("🎭  DiffyScan   🎭\n", GREEN)
    text += "  🎭  🎭  🎭  🎭"
    print(text)


def divider():
    print("\n" + " 🍥 " * 20 + "\n")