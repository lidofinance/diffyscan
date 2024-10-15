from .logger import logger


class BaseCustomException(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CompileError(BaseCustomException):
    def __init__(self, reason: str):
        super().__init__(f"Failed to compile contract: {reason}")


class NodeError(BaseCustomException):
    def __init__(self, reason: str):
        super().__init__(f"Failed to receive bytecode from node: {reason}")


class CalldataError(BaseCustomException):
    def __init__(self, reason: str):
        super().__init__(f"Failed to get calldata: {reason}")


class EncoderError(BaseCustomException):
    def __init__(self, reason: str):
        super().__init__(f"Failed to encode calldata arguments: {reason}")


class HardhatError(BaseCustomException):
    def __init__(self, reason: str):
        super().__init__(f"Failed to start Hardhat: {reason}")


class ExplorerError(BaseCustomException):
    def __init__(self, reason: str):
        super().__init__(f"Failed to communicate with Blockchain explorer: {reason}")


class BinVerifierError(BaseCustomException):
    def __init__(self, reason: str):
        super().__init__(f"Failed in binary comparison: {reason}")


class ExceptionHandler:
    raise_exception = True

    @staticmethod
    def initialize(raise_exception: bool) -> None:
        ExceptionHandler.raise_exception = raise_exception

    @staticmethod
    def raise_exception_or_log(custom_exception: BaseCustomException) -> None:
        if ExceptionHandler.raise_exception:
            raise custom_exception
        logger.error(str(custom_exception))
