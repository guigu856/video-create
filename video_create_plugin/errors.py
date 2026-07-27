"""Plugin 稳定错误。"""

from pydantic import JsonValue

from .contracts import ErrorBody, ErrorResponse, StableId


class PluginError(RuntimeError):
    def __init__(
        self,
        code: StableId,
        message: str,
        *,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error=ErrorBody(
                code=self.code,
                message=self.message,
                details=self.details,
            )
        )
