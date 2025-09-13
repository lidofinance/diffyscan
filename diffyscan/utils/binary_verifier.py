from .logger import logger, bgYellow, bgRed, bgGreen, red, green, to_hex
from .constants import OPCODES, PUSH0, PUSH32
from .custom_exceptions import BinVerifierError


def format_bytecode(bytecode: str) -> str:
    """Converts raw hex for an instruction into a '0x' prefixed string, or empty if none."""
    return "0x" + bytecode[2:] if len(bytecode) > 2 else ""


def trim_solidity_meta(bytecode: str) -> dict:
    """
    Strips Solidity metadata from the end of the bytecode, if present.
    Solidity appends a CBOR metadata section at the end, indicated by
    the last 2 bytes in big-endian (multiplied by 2 for hex, plus 4).

    Strips string constants from the end of the bytecode, if present.
    5b5056fe used to prevent executor wander into constant string or CBOR metadata
    """
    meta_size = int(bytecode[-4:], 16) * 2 + 4

    if meta_size > len(bytecode):
        return {"bytecode": bytecode, "metadata": "", "string_literal": ""}

    stop_opcode = "5b5056fe"

    if stop_opcode not in bytecode:
        return {
            "bytecode": bytecode,
            "metadata": bytecode[-meta_size:],
            "string_literal": "",
        }

    stop_index = bytecode.index(stop_opcode)

    return {
        "bytecode": bytecode[:-stop_index],
        "string_literal": bytes.fromhex(
            bytecode[stop_index + len(stop_opcode) : -meta_size]
        ).decode("ascii"),
        "metadata": bytecode[-meta_size:],
    }


def parse(bytecode: str):
    """
    Parses raw hex EVM bytecode into a list of instructions:
      [ { 'start': offset, 'length': N, 'op': {...}, 'bytecode': '...' }, ... ]
    """
    buffer = bytes.fromhex(bytecode[2:] if bytecode.startswith("0x") else bytecode)
    instructions = []
    i = 0
    unknown_opcodes = set()

    while i < len(buffer):
        opcode = buffer[i]
        if opcode not in OPCODES:
            unknown_opcodes.add(hex(opcode))

        # For PUSH1..PUSH32, the length is 1 + (opcode - PUSH0)
        length = 1 + (opcode - PUSH0 if PUSH0 <= opcode <= PUSH32 else 0)

        instr_hex = buffer[i : i + length].hex()
        instructions.append(
            {
                "start": i,
                "length": length,
                "op": {"name": OPCODES.get(opcode, "INVALID"), "code": opcode},
                "bytecode": instr_hex,
            }
        )

        i += length

    return instructions, unknown_opcodes


def regions_overlap(a_start: int, a_len: int, b_start: int, b_len: int) -> bool:
    """
    Return True if [a_start, a_start+a_len) overlaps with [b_start, b_start+b_len).
    """
    a_end = a_start + a_len
    b_end = b_start + b_len
    # intervals do NOT overlap if one is entirely to the left of the other
    if a_end <= b_start or b_end <= a_start:
        return False
    return True


def overlaps_any_immutable(
    immutables: dict[int, int], instr_start: int, instr_len: int
) -> bool:
    """
    Checks if the instruction byte range [instr_start.. instr_start+instr_len)
    overlaps with ANY known immutable region [start.. start+length) from 'immutables'.
    """
    for imm_start, imm_len in immutables.items():
        if regions_overlap(instr_start, instr_len, imm_start, imm_len):
            return True
    return False


def deep_match_bytecode(
    actual_bytecode: str, expected_bytecode: str, immutables: dict
) -> None:
    """
    Compare two chunks of bytecode instruction-by-instruction, ignoring differences
    that appear within known 'immutable' regions.

    If:
      - No differences => "Bytecodes fully match."
      - Differences only in immutables => "Bytecodes have differences only on the immutable reference position."
      - Differences outside immutables => raises BinVerifierError.
    """
    logger.info("Comparing actual code with the expected one...")

    # Possibly strip out metadata from both
    actual_trimmed = trim_solidity_meta(actual_bytecode)
    expected_trimmed = trim_solidity_meta(expected_bytecode)

    if actual_trimmed["metadata"] or expected_trimmed["metadata"]:
        logger.info("Metadata has been detected and trimmed")

    # Parse instructions
    actual_instructions, unknown_opcodes_a = parse(actual_trimmed["bytecode"])
    expected_instructions, unknown_opcodes_b = parse(expected_trimmed["bytecode"])

    # Check for unknown opcodes
    unknown_opcodes = unknown_opcodes_a | unknown_opcodes_b
    if unknown_opcodes:
        logger.warn(f"Detected unknown opcodes: {unknown_opcodes}")

    # If they differ in length, we still attempt to compare
    if len(actual_instructions) != len(expected_instructions):
        logger.warn("Codes have a different length")

    if actual_trimmed["string_literal"] != expected_trimmed["string_literal"]:
        logger.error("String literals don't match")
        logger.error("Expected: %s", expected_trimmed["string_literal"])
        logger.error("Actual: %s", actual_trimmed["string_literal"])
    elif actual_trimmed["string_literal"]:
        logger.warn(
            f"String literals found. Make sure it's not op code.\n{actual_trimmed['string_literal']}"
        )

    # Pair them up by index
    zipped_instructions = list(zip(actual_instructions, expected_instructions))

    # Identify mismatch indexes
    def is_mismatch(pair) -> bool:
        return pair[0]["bytecode"] != pair[1]["bytecode"]

    mismatches = [
        idx for idx, pair in enumerate(zipped_instructions) if is_mismatch(pair)
    ]

    # If no mismatches at all => fully match
    if not mismatches and len(actual_instructions) == len(expected_instructions):
        logger.okay("Bytecodes fully match")
        return

    # We'll show a few lines around each mismatch for context
    near_lines_count = 3
    checkpoints = {0, *mismatches}
    # handle last line if instructions differ in count
    if actual_instructions:
        checkpoints.add(len(actual_instructions) - 1)
    if expected_instructions:
        checkpoints.add(len(expected_instructions) - 1)

    # Expand around mismatches
    for ind in list(checkpoints):
        start_idx = max(0, ind - near_lines_count)
        end_idx = min(ind + near_lines_count, len(zipped_instructions) - 1)
        checkpoints.update(range(start_idx, end_idx + 1))

    checkpoints = sorted(checkpoints)

    # Print a small legend
    logger.divider()
    logger.info("0000 00 STOP - both expected and actual bytecode instructions match")
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

    # Print the diff lines
    # note: for shortness, we won't handle "None" instructions here,
    # since we used zip() not zip_longest(). Adjust if needed.
    for prev_idx, cur_idx in zip(checkpoints, checkpoints[1:]):
        if prev_idx != cur_idx - 1:
            print("...")

        actual = zipped_instructions[cur_idx][0]
        expected = zipped_instructions[cur_idx][1]

        # Compare opcodes
        same_opcode = actual["op"]["code"] == expected["op"]["code"]
        if same_opcode:
            opcode = to_hex(actual["op"]["code"])
            opname = actual["op"]["name"]
        else:
            opcode = (
                bgRed(to_hex(actual["op"]["code"]))
                + " "
                + bgGreen(to_hex(expected["op"]["code"]))
            )
            opname = bgRed(actual["op"]["name"]) + " " + bgGreen(expected["op"]["name"])

        actual_params = format_bytecode(actual["bytecode"])
        expected_params = format_bytecode(expected["bytecode"])

        # Check partial overlap with immutables
        instr_start = expected["start"]
        instr_len = expected["length"]
        within_immutable_region = overlaps_any_immutable(
            immutables, instr_start, instr_len
        )

        if actual_params == expected_params:
            # Perfect match => no highlight
            params = actual_params
        else:
            # There's a difference
            if within_immutable_region:
                params = bgYellow(actual_params) + " " + bgGreen(expected_params)
            else:
                params = bgRed(actual_params) + " " + bgGreen(expected_params)
                is_matched_with_excluded_immutables = False

        print(f"{to_hex(cur_idx, 4)} {opcode} {opname} {params}")

    # If we found any mismatch outside immutables => fail
    if not is_matched_with_excluded_immutables:
        raise BinVerifierError(
            "Bytecodes have differences not on the immutable reference position"
        )

    # Otherwise, differences exist but only in immutables
    logger.okay("Bytecodes have differences only on the immutable reference position")
