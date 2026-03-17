from .logger import logger


class BaseCustomException(Exception):
    prefix = ""

    def __init__(self, reason: str):
        message = f"{self.prefix}: {reason}" if self.prefix else reason
        super().__init__(message)
        self.message = message


class CompileError(BaseCustomException):
    prefix = "Failed to compile contract"


class NodeError(BaseCustomException):
    prefix = "Failed to communicate with RPC node"


class CalldataError(BaseCustomException):
    prefix = "Failed to get calldata"


class EncoderError(BaseCustomException):
    prefix = "Failed to encode calldata arguments"


class ExplorerError(BaseCustomException):
    prefix = "Failed to communicate with a remote resource"


class BinVerifierError(BaseCustomException):
    prefix = "Failed in binary comparison"


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
