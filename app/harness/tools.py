import time
from dataclasses import dataclass
from typing import Callable, List
from collections import OrderedDict
from pydantic import BaseModel, ValidationError
from app.harness.tracing import child_span, detect, event


class ToolError(Exception):
    pass


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type  # a pydantic BaseModel subclass
    fn: Callable  # takes the validated model instance, returns a dict
    dangerous: bool = False  # True for anything that mutates state


@dataclass
class ToolCall:
    name: str
    args: dict
    ok: bool
    result: dict | None
    error: str | None
    duration_ms: int


class ToolRegistry:
    def __init__(self):
        self._tools: "OrderedDict[str, ToolSpec]" = OrderedDict()
        self.CALLS: List[ToolCall] = []

    # Expose tools as a list of ToolSpec for tests that iterate over registry.tools
    @property
    def tools(self) -> List[ToolSpec]:
        return list(self._tools.values())

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ToolError(f'tool already registered: {spec.name}')
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        if name in self._tools:
            return self._tools[name]
        raise ToolError(f'unknown tool: {name}')

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def schemas(self) -> List[dict]:
        schemas: List[dict] = []
        for spec in self._tools.values():
            schemas.append(
                {
                    'name': spec.name,
                    'description': spec.description,
                    'dangerous': spec.dangerous,
                    'parameters': spec.args_model.model_json_schema(),
                }
            )
        return schemas

    def describe(self) -> str:
        lines: List[str] = []
        for spec in self._tools.values():
            arg_names = self._arg_names(spec.args_model)
            lines.append(f"{spec.name}({', '.join(arg_names)}) - {spec.description}")
        return "\n".join(lines)

    def call(self, name: str, args: dict) -> ToolCall:
        start = time.time()
        with child_span(name=f'tool:{name}', kind='TOOL', tool_name=name):
            if name not in self._tools:
                duration_ms = int((time.time() - start) * 1000)
                call = ToolCall(
                    name=name,
                    args=args,
                    ok=False,
                    result=None,
                    error=f'unknown tool: {name}',
                    duration_ms=duration_ms,
                )
                self.CALLS.append(call)
                detect('unknown tool requested', tool=name)
                return call

            spec = self._tools[name]

            try:
                validated = spec.args_model(**args)
            except ValidationError as e:
                duration_ms = int((time.time() - start) * 1000)
                call = ToolCall(
                    name=name,
                    args=args,
                    ok=False,
                    result=None,
                    error=f'invalid arguments: {e}',
                    duration_ms=duration_ms,
                )
                self.CALLS.append(call)
                detect('tool arguments rejected', tool=name, error=str(e))
                return call

            try:
                result = spec.fn(validated)
                duration_ms = int((time.time() - start) * 1000)
                if isinstance(result, dict):
                    final = result
                else:
                    final = {'value': result}
                call = ToolCall(
                    name=name,
                    args=args,
                    ok=True,
                    result=final,
                    error=None,
                    duration_ms=duration_ms,
                )
                self.CALLS.append(call)

                if isinstance(result, dict) and result.get('refused'):
                    detect('tool refused by policy', tool=name, reason=result.get('reason'))
                else:
                    event('tool call ok', tool=name, duration_ms=duration_ms)
                return call
            except Exception as e:
                duration_ms = int((time.time() - start) * 1000)
                call = ToolCall(
                    name=name,
                    args=args,
                    ok=False,
                    result=None,
                    error=str(e),
                    duration_ms=duration_ms,
                )
                self.CALLS.append(call)
                detect('tool execution failed', tool=name, error=str(e))
                return call

    def history(self) -> List[ToolCall]:
        return self.CALLS

    def reset(self) -> None:
        self.CALLS = []

    @staticmethod
    def _arg_names(model_cls: type) -> List[str]:
        # Prefer Pydantic v2 interface
        if hasattr(model_cls, 'model_fields'):
            try:
                return list(model_cls.model_fields.keys())
            except Exception:
                pass
        # Fallback for older patterns
        if hasattr(model_cls, '__fields__'):
            return list(model_cls.__fields__.keys())
        return []
