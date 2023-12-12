import argparse

parser = argparse.ArgumentParser()
parser.add_argument(
    "--support-brownie",
    help="Support recursive retrieving for contracts based on brownie framework.",
    action=argparse.BooleanOptionalAction,
)
