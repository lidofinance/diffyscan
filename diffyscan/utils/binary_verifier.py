import itertools

from .logger import logger, bgYellow, bgRed, bgGreen, red, green, to_hex
from .constants import OPCODES, PUSH0, PUSH32
from .custom_exceptions import BinVerifierError


def format_bytecode(bytecode):
    return "0x" + bytecode[2:] if len(bytecode) > 2 else ""


def trim_solidity_meta(bytecode: str) -> dict:
    meta_size = int(bytecode[-4:], 16) * 2 + 4

    if meta_size > len(bytecode):
        return {"bytecode": bytecode, "metadata": ""}

    return {
        "bytecode": bytecode[:-meta_size],
        "metadata": bytecode[-meta_size:],
    }


def deep_match_bytecode(
    actual_bytecode: str, expected_bytecode: str, immutables: dict
) -> None:
    logger.info("Comparing actual code with the expected one...")

    actual_trimmed_bytecode = trim_solidity_meta(actual_bytecode)
    expected_trimmed_bytecode = trim_solidity_meta(expected_bytecode)

    if actual_trimmed_bytecode["metadata"] or expected_trimmed_bytecode["metadata"]:
        logger.info("Metadata has been detected and trimmed")

    actual_instructions, unknown_opcodes_first_half = parse(
        actual_trimmed_bytecode["bytecode"]
    )
    expected_instructions, unknown_opcodes_second_half = parse(
        expected_trimmed_bytecode["bytecode"]
    )

    unknown_opcodes = (
        unknown_opcodes_first_half or set() | unknown_opcodes_second_half or set()
    )
    if unknown_opcodes:
        logger.warn(f"Detected unknown opcodes: {unknown_opcodes}")

    if len(actual_instructions) != len(expected_instructions):
        logger.warn(f"Codes have a different length")

    zipped_instructions = list(
        itertools.zip_longest(actual_instructions, expected_instructions)
    )

    is_mismatch = (
        lambda pair: pair[0] is None
        or pair[1] is None
        or pair[0].get("bytecode") != pair[1].get("bytecode")
    )
    mismatches = [
        index for index, pair in enumerate(zipped_instructions) if is_mismatch(pair)
    ]

    near_lines_count = 3  # context depth, i.e., the number of lines above and \below to be displayed for each diff

    checkpoints = {0, *mismatches}

    if actual_instructions:
        checkpoints.add(len(actual_instructions) - 1)

    if expected_instructions:
        checkpoints.add(len(expected_instructions) - 1)

    for ind in list(checkpoints):
        start_index = max(0, ind - near_lines_count)
        end_index = min(ind + near_lines_count, len(zipped_instructions) - 1)

        checkpoints.update(range(start_index, end_index + 1))

    checkpoints = sorted(checkpoints)

    logger.divider()
    logger.info(f"0000 00 STOP - both expected and actual bytecode instructions match")
    logger.info(f'{bgRed("0x0002")} - the actual bytecode differs')
    logger.info(
        f'{bgYellow("0x0001")} - the actual bytecode differs on the immutable reference position'
    )
    logger.info(
        f'{bgGreen("0x0003")} - the expected bytecode value when it doesn\'t match the actual one'
    )
    logger.info(
        f'{red("0000 00 STOP")} - the actual bytecode instruction doesn\'t exist, but expected is present'
    )
    logger.info(
        f'{green("0000 00 STOP")} - the actual bytecode instruction exists when the expected doesn\'t'
    )
    logger.divider()

    is_matched_with_excluded_immutables = True
    for previous_index, current_index in zip(checkpoints, checkpoints[1:]):
        if previous_index != current_index - 1:
            print("...")

        actual = (
            actual_instructions[current_index]
            if current_index < len(actual_instructions)
            else None
        )
        expected = (
            expected_instructions[current_index]
            if current_index < len(expected_instructions)
            else None
        )

        if not actual and expected:
            params = "0x" + expected["bytecode"][2:]
            print(
                red(
                    f'{to_hex(current_index, 4)} {to_hex(expected["op"]["code"])} {expected["op"]["name"]} {params}'
                )
            )
        elif actual and not expected:
            params = "0x" + actual["bytecode"][2:]
            print(
                green(
                    f'{to_hex(current_index, 4)} {to_hex(actual["op"]["code"])} {actual["op"]["name"]} {params}'
                )
            )
        elif actual and expected:
            opcode = (
                to_hex(actual["op"]["code"])
                if actual["op"]["code"] == expected["op"]["code"]
                else bgRed(to_hex(actual["op"]["code"]))
                + " "
                + bgGreen(to_hex(expected["op"]["code"]))
            )
            opname = (
                actual["op"]["name"]
                if actual["op"]["name"] == expected["op"]["name"]
                else bgRed(actual["op"]["name"]) + " " + bgGreen(expected["op"]["name"])
            )

            actual_params = format_bytecode(actual["bytecode"])
            expected_params = format_bytecode(expected["bytecode"])

            params_length = len(expected["bytecode"]) // 2 - 1
            is_immutable = immutables.get(expected["start"] + 1) == params_length
            if actual_params != expected_params and not is_immutable:
                is_matched_with_excluded_immutables = False
            params = (
                actual_params
                if actual_params == expected_params
                else (
                    bgYellow(actual_params) + " " + bgGreen(expected_params)
                    if is_immutable
                    else bgRed(actual_params) + " " + bgGreen(expected_params)
                )
            )
            print(f"{to_hex(current_index, 4)} {opcode} {opname} {params}")
        else:
            raise BinVerifierError("Invalid bytecode difference data")

    if not is_matched_with_excluded_immutables:
        raise BinVerifierError(
            f"Bytecodes have differences not on the immutable reference position"
        )

    logger.okay(f"Bytecodes have differences only on the immutable reference position")


def parse(bytecode):
    buffer = bytes.fromhex(bytecode[2:] if bytecode.startswith("0x") else bytecode)
    instructions = []
    i = 0
    unknown_opcodes = set()
    while i < len(buffer):
        opcode = buffer[i]
        if opcode not in OPCODES:
            unknown_opcodes.add(hex(opcode))
        length = 1 + (opcode - PUSH0 if PUSH0 <= opcode <= PUSH32 else 0)
        instructions.append(
            {
                "start": i,
                "length": length,
                "op": {"name": OPCODES.get(opcode, "INVALID"), "code": opcode},
                "bytecode": buffer[i : i + length].hex(),
            }
        )
        i += length
    return instructions, unknown_opcodes
