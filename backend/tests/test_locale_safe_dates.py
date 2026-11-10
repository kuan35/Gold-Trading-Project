"""Windows strftime encodes the format with the system locale, so 年/月/日 fail on English Windows."""
import ast
from pathlib import Path

PRODUCT = Path(__file__).resolve().parents[2]


def test_strftime_formats_are_ascii_only():
    offenders = []
    for folder in ('backend', 'scripts', 'research'):
        for path in sorted((PRODUCT / folder).rglob('*.py')):
            if 'tests' in path.parts or '.venv' in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'strftime':
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and not arg.value.isascii():
                            offenders.append(f'{path.relative_to(PRODUCT).as_posix()}:{node.lineno}')
    assert offenders == []
