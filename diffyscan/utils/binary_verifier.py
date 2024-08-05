from .logger import *
from .constants import OPCODES


def to_match(actualBytecode, expectedBytecode, immutables, remote_contract_address):
    logger.info("Comparing actual code with the expected one...")

    actualInstructions = parse(actualBytecode)
    expectedInstructions = parse(expectedBytecode)
    maxInstructionsCount = max(len(actualInstructions), len(expectedInstructions))

    differences = []
    for i in range(maxInstructionsCount):
        actual = actualInstructions[i] if i < len(actualInstructions) else None
        expected = expectedInstructions[i] if i < len(expectedInstructions) else None
        if not actual and not expected:
            raise ValueError("Invalid instructions data")
        elif (actual is not None) and (
            actual.get("bytecode") != expected.get("bytecode")
        ):
            differences.append(i)

    if not differences:
        logger.okay(f"Bytecodes are fully matched (contract {remote_contract_address})")
        return
    logger.warn(f"Bytecodes have differences contract {remote_contract_address})")

    nearLinesCount = 3
    checkpoints = {0, *differences}

    if actualInstructions:
        checkpoints.add(len(actualInstructions) - 1)

    if expectedInstructions:
        checkpoints.add(len(expectedInstructions) - 1)

    for ind in list(checkpoints):
        startIndex = max(0, ind - nearLinesCount)
        lastIndex = min(ind + nearLinesCount, maxInstructionsCount - 1)
        for i in range(startIndex, lastIndex + 1):
            checkpoints.add(i)

    checkpointsArray = sorted(list(checkpoints))

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
    for i in range(len(checkpointsArray)):
        currInd = checkpointsArray[i]
        prevInd = checkpointsArray[i - 1] if i > 0 else None
        if prevInd and prevInd != currInd - 1:
            print("...")

        actual = (
            actualInstructions[currInd] if currInd < len(actualInstructions) else None
        )
        expected = (
            expectedInstructions[currInd]
            if currInd < len(expectedInstructions)
            else None
        )

        if not actual and expected:
            params = "0x" + expected["bytecode"][2:]
            print(
                logger.red(
                    f'{to_hex(currInd, 4)} {to_hex(expected["op"]["code"])} {expected["op"]["name"]} {params}'
                )
            )
        elif actual and not expected:
            params = "0x" + actual["bytecode"][2:]
            print(
                logger.green(
                    f'{to_hex(currInd, 4)} {to_hex(actual["op"]["code"])} {actual["op"]["name"]} {params}'
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
            actualParams = (
                "0x" + actual["bytecode"][2:] if len(actual["bytecode"]) > 2 else ""
            )
            expectedParams = (
                "0x" + expected["bytecode"][2:] if len(expected["bytecode"]) > 2 else ""
            )

            paramsLength = len(expected["bytecode"]) // 2 - 1
            isImmutable = immutables.get(expected["start"] + 1) == paramsLength
            params = (
                actualParams
                if actualParams == expectedParams
                else (
                    bgYellow(actualParams) + " " + bgGreen(expectedParams)
                    if isImmutable
                    else bgRed(actualParams) + " " + bgGreen(expectedParams)
                )
            )
            print(f"{to_hex(currInd, 4)} {opcode} {opname} {params}")
        else:
            raise ValueError("Invalid bytecode difference data")


def parse(bytecode):
    buffer = bytes.fromhex(bytecode[2:] if bytecode.startswith("0x") else bytecode)
    instructions = []
    i = 0
    while i < len(buffer):
        opcode = buffer[i]
        length = 1 + (opcode - 0x5F if 0x5F <= opcode <= 0x7F else 0)
        instructions.append(
            {
                "start": i,
                "length": length,
                "op": {"name": OPCODES.get(opcode, "INVALID"), "code": opcode},
                "bytecode": buffer[i : i + length].hex(),
            }
        )
        i += length
    return instructions
