import time
import os
import tempfile

DIGEST_DIR = "digest"
START_TIME = time.time()
START_TIME_INT = int(START_TIME)
DIFFS_DIR = f"{DIGEST_DIR}/{START_TIME_INT}/diffs"
LOGS_PATH = f"{DIGEST_DIR}/{START_TIME_INT}/logs.txt"
DEFAULT_CONFIG_PATH = "config.json"
DEFAULT_HARDHAT_CONFIG_PATH = "hardhat_config.js"

SOLC_DIR = os.path.join(tempfile.gettempdir(), "solc_builds")

# fmt: off
OPCODES = {
    0x00: 'STOP', 0x01: 'ADD', 0x02: 'MUL', 0x03: 'SUB', 0x04: 'DIV', 0x05: 'SDIV',
    0x06: 'MOD', 0x07: 'SMOD', 0x08: 'ADDMOD', 0x09: 'MULMOD', 0x0A: 'EXP', 0x0B: 'SIGNEXTEND',
    0x10: 'LT', 0x11: 'GT', 0x12: 'SLT', 0x13: 'SGT', 0x14: 'EQ', 0x15: 'ISZERO', 0x16: 'AND',
    0x17: 'OR', 0x18: 'XOR', 0x19: 'NOT', 0x1A: 'BYTE', 0x1B: 'SHL', 0x1C: 'SHR', 0x1D: 'SAR',
    0x20: 'SHA3',
    0x30: 'ADDRESS', 0x31: 'BALANCE', 0x32: 'ORIGIN', 0x33: 'CALLER',
    0x34: 'CALLVALUE', 0x35: 'CALLDATALOAD', 0x36: 'CALLDATASIZE', 0x37: 'CALLDATACOPY',
    0x38: 'CODESIZE', 0x39: 'CODECOPY', 0x3A: 'GASPRICE', 0x3B: 'EXTCODESIZE',
    0x3C: 'EXTCODECOPY', 0x3D: 'RETURNDATASIZE', 0x3E: 'RETURNDATACOPY', 0x3F: 'EXTCODEHASH',
    0x40: 'BLOCKHASH', 0x41: 'COINBASE', 0x42: 'TIMESTAMP', 0x43: 'NUMBER',
    0x44: 'PREVRANDAO', 0x45: 'GASLIMIT', 0x46: 'CHAINID', 0x47: 'SELFBALANCE', 0x48: 'BASEFEE',
    0x50: 'POP', 0x51: 'MLOAD', 0x52: 'MSTORE', 0x53: 'MSTORE8',
    0x54: 'SLOAD', 0x55: 'SSTORE', 0x56: 'JUMP', 0x57: 'JUMPI',
    0x58: 'PC', 0x59: 'MSIZE', 0x5A: 'GAS', 0x5B: 'JUMPDEST',
    0x5F: 'PUSH0', 0x60: 'PUSH1', 0x61: 'PUSH2', 0x62: 'PUSH3', 0x63: 'PUSH4', 0x64: 'PUSH5',
    0x65: 'PUSH6', 0x66: 'PUSH7', 0x67: 'PUSH8', 0x68: 'PUSH9', 0x69: 'PUSH10', 0x6A: 'PUSH11',
    0x6B: 'PUSH12', 0x6C: 'PUSH13', 0x6D: 'PUSH14', 0x6E: 'PUSH15', 0x6F: 'PUSH16', 0x70: 'PUSH17',
    0x71: 'PUSH18', 0x72: 'PUSH19', 0x73: 'PUSH20', 0x74: 'PUSH21', 0x75: 'PUSH22', 0x76: 'PUSH23',
    0x77: 'PUSH24', 0x78: 'PUSH25', 0x79: 'PUSH26', 0x7A: 'PUSH27', 0x7B: 'PUSH28', 0x7C: 'PUSH29',
    0x7D: 'PUSH30', 0x7E: 'PUSH31', 0x7F: 'PUSH32',
    0x80: 'DUP1', 0x81: 'DUP2', 0x82: 'DUP3', 0x83: 'DUP4',
    0x84: 'DUP5', 0x85: 'DUP6', 0x86: 'DUP7', 0x87: 'DUP8',
    0x88: 'DUP9', 0x89: 'DUP10', 0x8A: 'DUP11', 0x8B: 'DUP12',
    0x8C: 'DUP13', 0x8D: 'DUP14', 0x8E: 'DUP15', 0x8F: 'DUP16',
    0x90: 'SWAP1', 0x91: 'SWAP2', 0x92: 'SWAP3', 0x93: 'SWAP4',
    0x94: 'SWAP5', 0x95: 'SWAP6', 0x96: 'SWAP7', 0x97: 'SWAP8',
    0x98: 'SWAP9', 0x99: 'SWAP10', 0x9A: 'SWAP11', 0x9B: 'SWAP12',
    0x9C: 'SWAP13', 0x9D: 'SWAP14', 0x9E: 'SWAP15', 0x9F: 'SWAP16',
    0xA0: 'LOG0', 0xA1: 'LOG1', 0xA2: 'LOG2', 0xA3: 'LOG3', 0xA4: 'LOG4',
    0xF0: 'CREATE', 0xF1: 'CALL', 0xF2: 'CALLCODE', 0xF3: 'RETURN', 0xF4: 'DELEGATECALL',
    0xF5: 'CREATE2', 0xFA: 'STATICCALL', 0xFD: 'REVERT', 0xFE: 'INVALID', 0xFF: 'SELFDESTRUCT',
}
# fmt: on


def get_key_from_value(dictinary: dict, value: str):
    keys = [
        dict_key for dict_key, dict_value in dictinary.items() if dict_value == value
    ]
    if keys:
        return keys[0]
    return None


PUSH0 = get_key_from_value(OPCODES, "PUSH0")
PUSH32 = get_key_from_value(OPCODES, "PUSH32")
