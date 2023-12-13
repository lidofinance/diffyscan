import argparse

parser = argparse.ArgumentParser()
parser.add_argument(
    "--support-brownie",
    help="Support recursive retrieving for contracts. It may be useful for contracts whose sources have been verified by the brownie tooling, which automatically replaces relative paths to contracts in imports with plain contract names.",
    action=argparse.BooleanOptionalAction,
)
