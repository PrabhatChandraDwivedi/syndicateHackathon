import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from pydantic import BaseModel

from app.harness.tools import ToolRegistry, ToolSpec, ToolCall, ToolError


def test_register_and_call_tool():
    registry = ToolRegistry()

    class Arg(BaseModel):
        a: int
        b: int

    def fn(args: Arg) -> dict:
        return {'sum': args.a + args.b}

    spec = ToolSpec(name='sum', description='sum two ints', args_model=Arg, fn=fn)
    registry.register(spec)

    call1 = registry.call('sum', {'a': 2, 'b': 3})
    assert call1.ok is True
    assert call1.result == {'sum': 5}

    call2 = registry.call('sum', {'a': 4, 'b': 5})
    assert call2.ok is True
    assert call2.result == {'sum': 9}

    history = registry.history()
    assert isinstance(history, list) and len(history) >= 2


def test_duplicate_registration_raises():
    registry = ToolRegistry()

    class Arg(BaseModel):
        x: int

    def f(args: Arg) -> dict:
        return {'x': args.x}

    spec = ToolSpec(name='dup', description='duplicate', args_model=Arg, fn=f)
    registry.register(spec)

    with pytest.raises(ToolError):
        registry.register(spec)


def test_get_unknown_name_raises():
    registry = ToolRegistry()
    with pytest.raises(ToolError):
        registry.get('unknown')


def test_call_unknown_tool_returns_error():
    registry = ToolRegistry()
    call = registry.call('boom', {})
    assert call.ok is False
    assert call.error is not None and 'unknown tool' in call.error


def test_invalid_args_validation_error():
    registry = ToolRegistry()

    class Arg(BaseModel):
        a: int

    executed = {'count': 0}

    def f(args: Arg) -> dict:
        executed['count'] += 1
        return {'a': args.a}

    spec = ToolSpec(name='boom', description='boom', args_model=Arg, fn=f)
    registry.register(spec)

    call = registry.call('boom', {'a': 'not-an-int'})
    assert call.ok is False
    assert call.error is not None and call.error.startswith('invalid arguments:')
    assert executed['count'] == 0


def test_tool_raises_exception():
    registry = ToolRegistry()

    class Arg(BaseModel):
        a: int

    def f(args: Arg) -> dict:
        raise ValueError('boom')

    spec = ToolSpec(name='crash', description='crash', args_model=Arg, fn=f)
    registry.register(spec)

    call = registry.call('crash', {'a': 1})
    assert call.ok is False
    assert call.error is not None and 'boom' in call.error


def test_schemas_contains_tool_and_schema():
    registry = ToolRegistry()

    class Arg(BaseModel):
        a: int
        b: int

    def f(args: Arg) -> dict:
        return {}

    spec = ToolSpec(name='pairs', description='two ints', args_model=Arg, fn=f)
    registry.register(spec)

    schemas = registry.schemas()
    assert isinstance(schemas, list) and len(schemas) == 1
    s = schemas[0]
    assert s.get('name') == 'pairs'
    assert s.get('description') == 'two ints'
    assert 'parameters' in s and isinstance(s['parameters'], dict)


def test_describe_order_and_names():
    registry = ToolRegistry()

    class Arg1(BaseModel):
        x: int

    def f1(args: Arg1) -> dict:
        return {'x_squared': args.x * args.x}

    spec1 = ToolSpec(name='square', description='square', args_model=Arg1, fn=f1)
    registry.register(spec1)

    class Arg2(BaseModel):
        y: int

    def f2(args: Arg2) -> dict:
        return {'y_times': args.y * 2}

    spec2 = ToolSpec(name='double', description='double', args_model=Arg2, fn=f2)
    registry.register(spec2)

    desc = registry.describe()
    lines = desc.splitlines()
    assert any(line.startswith('square(') for line in lines)
    assert any(line.startswith('double(') for line in lines)

    idx_square = next(i for i, line in enumerate(lines) if line.startswith('square('))
    idx_double = next(i for i, line in enumerate(lines) if line.startswith('double('))
    assert idx_square < idx_double


def test_history_and_reset():
    registry = ToolRegistry()

    class Arg(BaseModel):
        a: int

    def fn(args: Arg) -> dict:
        return {'a': args.a}

    spec = ToolSpec(name='id', description='identity', args_model=Arg, fn=fn)
    registry.register(spec)

    registry.call('id', {'a': 123})
    assert len(registry.history()) == 1
    registry.reset()
    assert len(registry.history()) == 0
