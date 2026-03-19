from .logger import logger, bgYellow, bgRed, bgGreen, red, green, to_hex
from .constants import OPCODES, PUSH0, PUSH32
from .custom_exceptions import BinVerifierError


def format_bytecode(bytecode: str) -> str:
    """Converts raw hex for an instruction into a '0x' prefixed string, or empty if none."""
    return "0x" + bytecode[2:] if len(bytecode) > 2 else ""


def trim_solidity_meta(bytecode: str) -> dict:
    """
    Strip Solidity metadata from the end of the bytecode, if present.

    Solidity appends a CBOR metadata section at the end, indicated by the last
    2 bytes in big-endian (multiplied by 2 for hex, plus 4).

    String constants may also be appended before metadata. The 5b5056fe marker
    is used to separate executable bytecode from trailing string data.
    """
    raw = bytecode[2:] if bytecode.startswith("0x") else bytecode
    if len(raw) < 4:
        return {"bytecode": _prefix_hex(raw), "metadata": "", "string_literal": ""}

    meta_size = int(raw[-4:], 16) * 2 + 4
    if meta_size > len(raw):
        return {"bytecode": _prefix_hex(raw), "metadata": "", "string_literal": ""}

    stop_opcode = "5b5056fe"
    metadata = raw[-meta_size:]

    if stop_opcode not in raw:
        return {
            "bytecode": _prefix_hex(raw[:-meta_size]),
            "metadata": _prefix_hex(metadata),
            "string_literal": "",
        }

    stop_index = raw.index(stop_opcode) + len(stop_opcode)
    string_literal = ""
    try:
        string_literal = bytes.fromhex(raw[stop_index:-meta_size]).decode("ascii")
    except (ValueError, UnicodeDecodeError):
        logger.warn("Failed to decode potential string literal from bytecode")

    return {
        "bytecode": _prefix_hex(raw[:stop_index]),
        "string_literal": string_literal,
        "metadata": _prefix_hex(metadata),
    }


def parse(bytecode: str):
    """
    Parse raw hex EVM bytecode into a list of instructions:
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
    """Return True if [a_start, a_start+a_len) overlaps [b_start, b_start+b_len)."""
    a_end = a_start + a_len
    b_end = b_start + b_len
    return not (a_end <= b_start or b_end <= a_start)


def overlaps_any_immutable(
    immutables: dict[int, int], instr_start: int, instr_len: int
) -> bool:
    """Return True if the byte range overlaps any known immutable region."""
    for imm_start, imm_len in immutables.items():
        if regions_overlap(instr_start, instr_len, imm_start, imm_len):
            return True
    return False


def analyze_bytecode_diff(
    local_bytecode: str,
    remote_bytecode: str,
    immutables: dict[int, int],
) -> dict:
    logger.info("Comparing actual code with the expected one...")

    local_trimmed = trim_solidity_meta(local_bytecode)
    remote_trimmed = trim_solidity_meta(remote_bytecode)

    local_runtime = local_trimmed["bytecode"]
    remote_runtime = remote_trimmed["bytecode"]

    local_instructions, unknown_opcodes_local = parse(local_runtime)
    remote_instructions, unknown_opcodes_remote = parse(remote_runtime)
    instruction_pairs = list(zip(local_instructions, remote_instructions))
    instruction_mismatches = [
        index
        for index, (local_instr, remote_instr) in enumerate(instruction_pairs)
        if local_instr["bytecode"] != remote_instr["bytecode"]
    ]

    runtime_mismatch_ranges = _compute_runtime_mismatch_ranges(
        local_runtime,
        remote_runtime,
        immutables,
    )
    immutable_observations = _collect_immutable_observations(
        local_runtime,
        remote_runtime,
        immutables,
    )

    string_literal_mismatch = (
        local_trimmed["string_literal"] != remote_trimmed["string_literal"]
    )
    metadata_mismatch = local_trimmed["metadata"] != remote_trimmed["metadata"]
    length_mismatch = len(_strip_prefix(local_runtime)) != len(
        _strip_prefix(remote_runtime)
    )
    exact_match = not (
        runtime_mismatch_ranges
        or metadata_mismatch
        or string_literal_mismatch
        or length_mismatch
    )

    return {
        "exact_match": exact_match,
        "local_runtime_bytecode": local_runtime,
        "remote_runtime_bytecode": remote_runtime,
        "local_metadata": local_trimmed["metadata"],
        "remote_metadata": remote_trimmed["metadata"],
        "local_string_literal": local_trimmed["string_literal"],
        "remote_string_literal": remote_trimmed["string_literal"],
        "runtime_mismatch_ranges": runtime_mismatch_ranges,
        "immutable_regions": dict(sorted(immutables.items())),
        "immutable_observations": immutable_observations,
        "metadata_mismatch": metadata_mismatch,
        "string_literal_mismatch": string_literal_mismatch,
        "length_mismatch": length_mismatch,
        "unknown_opcodes": sorted(unknown_opcodes_local | unknown_opcodes_remote),
        "local_instructions": local_instructions,
        "remote_instructions": remote_instructions,
        "instruction_mismatches": instruction_mismatches,
    }


def log_bytecode_diff_analysis(analysis: dict) -> None:
    if analysis["local_metadata"] or analysis["remote_metadata"]:
        logger.info("Metadata has been detected and trimmed")
    if analysis["unknown_opcodes"]:
        logger.warn(f"Detected unknown opcodes: {set(analysis['unknown_opcodes'])}")
    if analysis["length_mismatch"]:
        logger.warn("Codes have a different length")

    _log_string_literal_analysis(analysis)

    if not analysis["local_instructions"] or not analysis["remote_instructions"]:
        return

    if not analysis["instruction_mismatches"]:
        return

    checkpoints = _get_checkpoints_for_display(
        analysis["instruction_mismatches"],
        analysis["local_instructions"],
        analysis["remote_instructions"],
    )
    instruction_pairs = list(
        zip(analysis["local_instructions"], analysis["remote_instructions"])
    )

    _print_diff_legend()
    _print_instruction_diffs(
        instruction_pairs,
        checkpoints,
        analysis["immutable_regions"],
    )


def deep_match_bytecode(
    actual_bytecode: str,
    expected_bytecode: str,
    immutables: dict,
) -> bool:
    """
    Backward-compatible wrapper around bytecode analysis.

    Metadata-only differences are still ignored here. The CLI now uses the
    structured analysis result directly for granular allowlists.
    """
    analysis = analyze_bytecode_diff(actual_bytecode, expected_bytecode, immutables)

    if (
        not analysis["runtime_mismatch_ranges"]
        and not analysis["string_literal_mismatch"]
        and not analysis["length_mismatch"]
    ):
        logger.okay("Bytecodes match (after trimming metadata and string literals)")
        return True

    log_bytecode_diff_analysis(analysis)

    if analysis["length_mismatch"]:
        raise BinVerifierError(
            "Bytecodes have different length after trimming metadata and string literals"
        )

    if analysis["string_literal_mismatch"]:
        raise BinVerifierError("Bytecodes have different string literals")

    if any(
        not range_info["immutable"]
        for range_info in analysis["runtime_mismatch_ranges"]
    ):
        raise BinVerifierError(
            "Bytecodes have differences not on the immutable reference position"
        )

    logger.warn("Bytecodes have differences only on the immutable reference position")
    return False


def _compute_runtime_mismatch_ranges(
    local_runtime: str,
    remote_runtime: str,
    immutables: dict[int, int],
) -> list[dict]:
    local_hex = _strip_prefix(local_runtime)
    remote_hex = _strip_prefix(remote_runtime)
    comparable_byte_count = min(len(local_hex), len(remote_hex)) // 2

    ranges = []
    current_start = None

    for offset in range(comparable_byte_count):
        local_byte = local_hex[offset * 2 : offset * 2 + 2]
        remote_byte = remote_hex[offset * 2 : offset * 2 + 2]

        if local_byte != remote_byte and current_start is None:
            current_start = offset
            continue

        if local_byte == remote_byte and current_start is not None:
            ranges.append(
                _build_runtime_range(current_start, offset - current_start, immutables)
            )
            current_start = None

    if current_start is not None:
        ranges.append(
            _build_runtime_range(
                current_start,
                comparable_byte_count - current_start,
                immutables,
            )
        )

    return ranges


def _build_runtime_range(
    offset: int,
    length: int,
    immutables: dict[int, int],
) -> dict:
    return {
        "offset": offset,
        "length": length,
        "immutable": _range_is_fully_immutable(offset, length, immutables),
    }


def _range_is_fully_immutable(
    offset: int,
    length: int,
    immutables: dict[int, int],
) -> bool:
    return all(
        _offset_in_immutable(byte_offset, immutables)
        for byte_offset in range(offset, offset + length)
    )


def _offset_in_immutable(offset: int, immutables: dict[int, int]) -> bool:
    return any(start <= offset < start + length for start, length in immutables.items())


def _collect_immutable_observations(
    local_runtime: str,
    remote_runtime: str,
    immutables: dict[int, int],
) -> list[dict]:
    local_hex = _strip_prefix(local_runtime)
    remote_hex = _strip_prefix(remote_runtime)
    observations = []

    for offset, length in sorted(immutables.items()):
        local_value = _prefix_hex(slice_hex(local_hex, offset, length))
        remote_value = _prefix_hex(slice_hex(remote_hex, offset, length))
        observations.append(
            {
                "offset": offset,
                "length": length,
                "local_value": local_value,
                "remote_value": remote_value,
                "differs": local_value != remote_value,
            }
        )

    return observations


def _print_diff_legend():
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


def _get_checkpoints_for_display(
    mismatches,
    local_instructions,
    remote_instructions,
    context_lines=3,
):
    checkpoints = {0, *mismatches}
    max_idx = min(len(local_instructions), len(remote_instructions)) - 1
    if max_idx < 0:
        return [0]

    checkpoints.add(max_idx)

    for idx in list(checkpoints):
        start_idx = max(0, idx - context_lines)
        end_idx = min(idx + context_lines, max_idx)
        checkpoints.update(range(start_idx, end_idx + 1))

    return sorted(checkpoints)


def _format_instruction_diff(local_instruction, remote_instruction, immutables):
    same_opcode = local_instruction["op"]["code"] == remote_instruction["op"]["code"]
    if same_opcode:
        opcode = to_hex(local_instruction["op"]["code"])
        opname = local_instruction["op"]["name"]
    else:
        opcode = (
            bgRed(to_hex(local_instruction["op"]["code"]))
            + " "
            + bgGreen(to_hex(remote_instruction["op"]["code"]))
        )
        opname = (
            bgRed(local_instruction["op"]["name"])
            + " "
            + bgGreen(remote_instruction["op"]["name"])
        )

    local_params = format_bytecode(local_instruction["bytecode"])
    remote_params = format_bytecode(remote_instruction["bytecode"])
    within_immutable_region = overlaps_any_immutable(
        immutables,
        remote_instruction["start"],
        remote_instruction["length"],
    )

    is_immutable_only = True
    if local_params == remote_params:
        params = local_params
    elif within_immutable_region:
        params = bgYellow(local_params) + " " + bgGreen(remote_params)
    else:
        params = bgRed(local_params) + " " + bgGreen(remote_params)
        is_immutable_only = False

    if not same_opcode:
        is_immutable_only = False

    return (opcode, opname, params), is_immutable_only


def _print_instruction_diffs(instruction_pairs, checkpoints, immutables):
    for prev_idx, cur_idx in zip(checkpoints, checkpoints[1:]):
        if prev_idx != cur_idx - 1:
            print("...")

        local_instruction, remote_instruction = instruction_pairs[cur_idx]
        (opcode, opname, params), _ = _format_instruction_diff(
            local_instruction,
            remote_instruction,
            immutables,
        )
        print(f"{to_hex(cur_idx, 4)} {opcode} {opname} {params}")


def _log_string_literal_analysis(analysis: dict) -> None:
    if analysis["string_literal_mismatch"]:
        logger.error("String literals don't match")
        logger.error("Expected", analysis["remote_string_literal"])
        logger.error("Actual", analysis["local_string_literal"])
    elif analysis["local_string_literal"]:
        logger.warn(
            "String literals found",
            analysis["local_string_literal"],
        )


def slice_hex(hex_value: str, offset: int, length: int) -> str:
    start = offset * 2
    end = start + length * 2
    return hex_value[start:end]


def _prefix_hex(value: str) -> str:
    return f"0x{value}" if value else ""


def _strip_prefix(value: str) -> str:
    return value[2:] if value.startswith("0x") else value
