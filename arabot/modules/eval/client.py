import ast
import inspect
import sys
from collections.abc import Generator
from contextlib import _RedirectStream, contextmanager, redirect_stdout
from functools import partial
from io import StringIO
from types import CodeType
from typing import Any, TextIO

from aiohttp import ClientSession

from . import errors
from .abc import Evaluator


class stdin_from(_RedirectStream):  # noqa: N801
    _stream = "stdin"


class RemoteEval(Evaluator):
    API = "https://emkc.org/api/v2/piston/execute"

    def __init__(self, *, session: ClientSession, stdin: str = ""):
        self.session = session
        self.stdin = stdin

    async def fetch_response(self, code: str, *, stdin: str | None = None):
        options = {
            "language": "python",
            "version": "3",
            "files": [{"name": self.TB_FILENAME, "content": code}],
            "stdin": stdin or self.stdin,
        }
        async with self.session.post(self.API, json=options) as response:
            metadata = await response.json()

        if "message" in metadata:
            raise errors.RemoteEvalBadResponse(metadata["message"])

        response.raise_for_status()

        return metadata["run"]

    async def run(self, code: str, *, stdin: str | None = None) -> tuple[str, None]:
        data = await self.fetch_response(code, stdin=stdin or self.stdin)
        stdout = data["stdout"]

        if exit_code := data["code"]:
            raise errors.RemoteEvalException(data["stderr"], stdout, exit_code)

        return stdout, None


class LocalEval(Evaluator):
    def __init__(self, *, env: dict | None = None, stdin: TextIO | None = None):
        self.env = env or {}
        self.stdin = stdin or sys.stdin

    def compile(self, code: str | bytes, flags: int = 0) -> CodeType:
        compile_for = partial(compile, code, self.TB_FILENAME, flags=flags)
        try:
            try:
                return compile_for("eval")
            except SyntaxError:
                return compile_for("exec")
        except BaseException as exc:
            raise errors.LocalEvalCompileException(exc) from exc

    async def execute(self, compiled_code: CodeType) -> tuple[str, Any]:
        output_buffer = StringIO()
        try:
            with stdin_from(self.stdin), redirect_stdout(output_buffer):
                if compiled_code.co_flags & inspect.CO_COROUTINE:
                    r = await eval(compiled_code, self.env)
                else:
                    r = eval(compiled_code, self.env)
        except BaseException as exc:
            stdout = output_buffer.getvalue()
            raise errors.LocalEvalExecuteException(exc, stdout) from exc
        else:
            stdout = output_buffer.getvalue()
            return stdout, r

    async def run(
        self, code: str, *, env: dict[str, Any] | None = None, stdin: TextIO | None = None
    ) -> tuple[str, Any]:
        with self._lock(env=env or self.env, stdin=stdin or self.stdin):
            to_run = self.compile(code, ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            return await self.execute(to_run)

    @contextmanager
    def _lock(self, **overwrites) -> Generator[None]:
        """Set overwrites on self and then resets to initial state."""
        backup = self.__dict__.copy()
        self.__dict__ |= overwrites
        try:
            yield
        finally:
            for key in overwrites:
                if key in backup:
                    setattr(self, key, backup[key])
                elif hasattr(self, key):
                    delattr(self, key)
