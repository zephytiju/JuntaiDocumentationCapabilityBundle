"""Stable errors returned by library and CLI validation paths."""

from __future__ import annotations


class CapabilityError(ValueError):
    """A fail-closed capability contract violation."""

    code = "CAPABILITY_INVALID"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.code


def fail(code: str, message: str) -> NoReturn:
    raise CapabilityError(message, code=code)


from typing import NoReturn  # noqa: E402  (keeps public error declarations first)
