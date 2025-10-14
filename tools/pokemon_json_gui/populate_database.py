"""Populate the Pokémon JSON GUI database with fully populated entries."""

from __future__ import annotations

import ast
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from . import project_paths
    from .constants_loader import (
        load_enabled_family_macros,
        load_species_metadata,
        showdown_folder_from_species,
    )
    from .data_models import EvolutionEntry, LearnsetEntry, PokemonData
    from .database import PokemonDatabase
    from .file_manager import AssetBundle
except ImportError:  # pragma: no cover - executed when run as a script
    import sys

    module_path = Path(__file__).resolve().parent
    module_dir = str(module_path)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    import project_paths  # type: ignore
    from constants_loader import (  # type: ignore
        load_enabled_family_macros,
        load_species_metadata,
        showdown_folder_from_species,
    )
    from data_models import EvolutionEntry, LearnsetEntry, PokemonData  # type: ignore
    from database import PokemonDatabase  # type: ignore
    from file_manager import AssetBundle  # type: ignore


SPECIES_MARKER = "[SPECIES_"
PREPROC_HEADER = (
    "#include \"gba/defines.h\"\n"
    "#include \"config/general.h\"\n"
    "#include \"config/pokemon.h\"\n"
    "#include \"config/species_enabled.h\"\n"
    "#include \"constants/pokemon.h\"\n"
)
EV_YIELD_FIELDS = [
    ("evYield_HP", "hp"),
    ("evYield_Attack", "attack"),
    ("evYield_Defense", "defense"),
    ("evYield_SpAttack", "spAttack"),
    ("evYield_SpDefense", "spDefense"),
    ("evYield_Speed", "speed"),
]


def _species_family_mapping() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for path in sorted(project_paths.SPECIES_INFO_DIR.glob("*.h")):
        current_family: Optional[str] = None
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#if P_FAMILY_"):
                parts = stripped.split()
                if parts:
                    current_family = parts[1]
                continue
            if stripped.startswith("#endif"):
                if "P_FAMILY_" in stripped:
                    current_family = None
                continue
            if stripped.startswith(SPECIES_MARKER) and current_family:
                end = stripped.find("]")
                if end != -1:
                    species_name = stripped[len("[") : end]
                    mapping[species_name] = current_family
    return mapping


def _collect_enabled_species() -> List[str]:
    enabled_families = set(load_enabled_family_macros())
    mapping = _species_family_mapping()
    return [species for species, family in mapping.items() if family in enabled_families]


def _custom_species_source() -> Optional[str]:
    species_path = project_paths.REPO_ROOT / "src" / "data" / "pokemon" / "species_info.h"
    if not species_path.exists():
        return None

    text = species_path.read_text(encoding="utf-8")
    marker = "/* You may add any custom species below this point"
    marker_index = text.find(marker)
    if marker_index == -1:
        return None

    decl_marker = "const struct SpeciesInfo gSpeciesInfo[]"
    decl_index = text.find(decl_marker)
    if decl_index == -1:
        return None

    start = text.find("*/", marker_index)
    if start == -1:
        return None
    start += 2

    length = len(text)
    while True:
        while start < length and text[start].isspace():
            start += 1
        if start < length and text.startswith("/*", start):
            end_comment = text.find("*/", start)
            if end_comment == -1:
                return None
            start = end_comment + 2
            continue
        break

    end = text.rfind("};")
    if end == -1 or end <= start:
        return None

    custom_section = text[start:end]
    if not custom_section.strip():
        return None

    macro_section = text[:decl_index]
    macro_lines = []
    for line in macro_section.splitlines():
        stripped = line.strip()
        if stripped.startswith("#include \"species_info/gen_"):
            continue
        macro_lines.append(line)
    macro_section = "\n".join(macro_lines)

    return (
        f"{macro_section}\n"
        "const struct SpeciesInfo gSpeciesInfo[] = {\n"
        f"{custom_section}\n"
        "};\n"
    )


def _load_custom_species_info(header: Path) -> Dict[str, Dict[str, str]]:
    source = _custom_species_source()
    if source is None:
        return {}

    with tempfile.NamedTemporaryFile("w", suffix=".h", encoding="utf-8", delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(source)

    try:
        text = _run_cpp(temp_path, header)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:  # pragma: no cover - cleanup best effort
            pass

    return _parse_species_info_text(text)


def _pick_existing(base: Path, names: Iterable[str]) -> Optional[Path]:
    for name in names:
        candidate = base / name
        if candidate.exists():
            return candidate
    return None


def _resolve_asset_folder(folder: str) -> Optional[Tuple[Path, Path]]:
    direct = project_paths.GRAPHICS_ROOT / folder
    if direct.exists():
        return direct, direct

    parts = folder.split('_')
    if not parts:
        return None

    def _search(current: Path, remaining: List[str]) -> Optional[Path]:
        if not remaining:
            return current if current.exists() else None
        joined = '_'.join(remaining)
        candidate = current / joined
        if candidate.exists():
            return candidate
        for index in range(1, len(remaining) + 1):
            prefix = '_'.join(remaining[:index])
            candidate = current / prefix
            if candidate.exists():
                result = _search(candidate, remaining[index:])
                if result is not None:
                    return result
        return None

    for prefix_len in range(len(parts), 0, -1):
        base_name = '_'.join(parts[:prefix_len])
        base_path = project_paths.GRAPHICS_ROOT / base_name
        if not base_path.exists():
            continue
        remainder = parts[prefix_len:]
        resolved = _search(base_path, remainder)
        if resolved is not None:
            return resolved, base_path
        return base_path, base_path
    return None


def _build_asset_bundle(folder: str) -> Optional[AssetBundle]:
    resolved = _resolve_asset_folder(folder)
    if resolved is None:
        return None

    asset_base, fallback_base = resolved
    search_paths = [asset_base]
    if fallback_base not in search_paths:
        search_paths.append(fallback_base)

    def find_asset(names: Iterable[str]) -> Optional[Path]:
        for path in search_paths:
            candidate = _pick_existing(path, names)
            if candidate is not None:
                return candidate
        return None

    front = find_asset((
        "front.png",
        "anim_front.png",
        "front_hd.png",
        "front_gba.png",
        "anim_front_gba.png",
    ))
    back = find_asset((
        "back.png",
        "anim_back.png",
        "back_hd.png",
        "back_gba.png",
    ))
    icon = find_asset(("icon.png", "icon_gba.png"))
    normal_pal = find_asset(("normal.pal", "normal_gba.pal"))
    if not all((front, back, icon, normal_pal)):
        return None
    shiny_pal = find_asset(("shiny.pal", "shiny_gba.pal"))
    return AssetBundle(
        front=front,  # type: ignore[arg-type]
        back=back,  # type: ignore[arg-type]
        icon=icon,  # type: ignore[arg-type]
        normal_palette=normal_pal,  # type: ignore[arg-type]
        shiny_palette=shiny_pal,
        optional_assets={},
        cry_sample=None,
    )


def _run_cpp(path: Path, header: Path) -> str:
    include_root = project_paths.REPO_ROOT / "include"
    include_args = [
        "-I",
        str(include_root),
        "-I",
        str(include_root / "config"),
        "-I",
        str(include_root / "constants"),
    ]
    command = ["cpp", "-P", f"-include{header}"] + include_args + [str(path)]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"cpp failed for {path}: {result.stderr.strip()}")
    return result.stdout


def _count_brackets(text: str, paren: int, brace: int) -> Tuple[int, int]:
    in_string = False
    escape = False
    for char in text:
        if char == "\"" and not escape:
            in_string = not in_string
        if in_string:
            escape = char == "\\" and not escape
            continue
        escape = False
        if char == "(":
            paren += 1
        elif char == ")":
            paren -= 1
        elif char == "{":
            brace += 1
        elif char == "}":
            brace -= 1
    return paren, brace


def _split_top_level(text: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    paren = brace = 0
    in_string = False
    escape = False
    for char in text:
        if char == "\"" and not escape:
            in_string = not in_string
        if in_string:
            escape = char == "\\" and not escape
            current.append(char)
            continue
        escape = False
        if char == "(":
            paren += 1
        elif char == ")":
            paren -= 1
        elif char == "{":
            brace += 1
        elif char == "}":
            brace -= 1
        if char == "," and paren == 0 and brace == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_block_assignments(lines: Sequence[str]) -> Dict[str, str]:
    assignments: Dict[str, str] = {}
    current_field: Optional[str] = None
    buffer: List[str] = []
    paren = brace = 0
    expanded_lines: List[str] = []
    for raw_line in lines:
        if ', .' in raw_line:
            raw_line = raw_line.replace(', .', ',\n        .')
        expanded_lines.extend(raw_line.splitlines())
    for raw_line in expanded_lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        if current_field is None:
            if not stripped.startswith('.') or '=' not in stripped:
                continue
            field_part, value_part = stripped[1:].split('=', 1)
            current_field = field_part.strip()
            value = value_part.strip()
            has_comma = value.endswith(',')
            if has_comma:
                value = value[:-1].strip()
            buffer = [value]
            paren, brace = _count_brackets(value, 0, 0)
            if paren == 0 and brace == 0 and has_comma:
                assignments[current_field] = value
                current_field = None
                buffer = []
                paren = brace = 0
        else:
            value = stripped
            has_comma = value.endswith(',')
            if has_comma:
                value = value[:-1].strip()
            buffer.append(value)
            paren, brace = _count_brackets(value, paren, brace)
            if paren == 0 and brace == 0 and has_comma:
                assignments[current_field] = " ".join(buffer).strip()
                current_field = None
                buffer = []
                paren = brace = 0
    if current_field is not None and buffer:
        assignments[current_field] = " ".join(buffer).strip()
    return assignments


def _parse_species_info_text(text: str) -> Dict[str, Dict[str, str]]:
    result: Dict[str, Dict[str, str]] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        match = re.match(r"\[(SPECIES_[A-Z0-9_]+)\]\s*=", stripped)
        if not match:
            index += 1
            continue
        species = match.group(1)
        index += 1
        while index < len(lines) and '{' not in lines[index]:
            index += 1
        if index >= len(lines):
            break
        block_lines: List[str] = []
        brace_depth = 0
        while index < len(lines):
            line = lines[index]
            if '{' in line:
                brace_depth += line.count('{')
            if '}' in line:
                brace_depth -= line.count('}')
            block_lines.append(line)
            index += 1
            if brace_depth <= 0:
                break
        if len(block_lines) < 2:
            continue
        inner = block_lines[1:-1]
        assignments = _parse_block_assignments(inner)
        result[species] = assignments
    return result


def _extract_string(value: str) -> str:
    if not value:
        return ""
    text = value.strip()
    if text.startswith('_(') and text.endswith(')'):
        text = text[2:-1]
    if text.startswith('(') and text.endswith(')'):
        text = text[1:-1]
    strings = re.findall(r'"(?:\\.|[^\"])*"', text)
    if not strings:
        return text.strip()
    return "".join(ast.literal_eval(token) for token in strings)


def _parse_compound_string(value: str) -> str:
    if not value:
        return ""
    text = value.strip()
    if text.startswith('COMPOUND_STRING'):
        start = text.find('(')
        end = text.rfind(')')
        if start != -1 and end != -1:
            text = text[start + 1 : end]
    strings = re.findall(r'"(?:\\.|[^\"])*"', text)
    if not strings:
        return text.strip()
    return "".join(ast.literal_eval(token) for token in strings)


def _parse_macro_arguments(value: str) -> List[str]:
    if not value:
        return []
    text = value.strip()
    start = text.find('(')
    end = text.rfind(')')
    if start == -1 or end == -1 or end <= start:
        return [text]
    inner = text[start + 1 : end]
    return [part.strip() for part in _split_top_level(inner) if part.strip()]


def _parse_braced_list(value: str) -> List[str]:
    if not value:
        return []
    text = value.strip()
    if text.startswith('{') and text.endswith('}'):
        text = text[1:-1]
    return [part.strip() for part in _split_top_level(text) if part.strip()]


TOKEN_REGEX = re.compile(
    r"(?P<NUMBER>0x[0-9A-Fa-f]+|\d+)"
    r"|(?P<OP>==|!=|<=|>=|<<|>>|&&|\|\||[+\-*/%&|^~!?():<>])"
    r"|(?P<IDENT>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<WS>\s+)"
)
IDENT_VALUES = {"TRUE": 1, "FALSE": 0}


def _tokenize_expression(expr: str) -> List[Tuple[str, object]]:
    tokens: List[Tuple[str, object]] = []
    index = 0
    length = len(expr)
    while index < length:
        match = TOKEN_REGEX.match(expr, index)
        if not match:
            raise ValueError(f"Unsupported token in expression: {expr[index:]}" )
        index = match.end()
        kind = match.lastgroup
        value = match.group(kind)
        if kind == "WS":
            continue
        if kind == "NUMBER":
            tokens.append(("NUMBER", int(value, 0)))
        elif kind == "IDENT":
            mapped = IDENT_VALUES.get(value)
            if mapped is None:
                raise ValueError(f"Unknown identifier in expression: {value}")
            tokens.append(("NUMBER", mapped))
        else:  # OP
            tokens.append(("OP", value))
    tokens.append(("EOF", ""))
    return tokens


class _TokenStream:
    def __init__(self, tokens: List[Tuple[str, object]]):
        self._tokens = tokens
        self._index = 0

    def peek(self) -> Tuple[str, object]:
        return self._tokens[self._index]

    def next(self) -> Tuple[str, object]:
        token = self._tokens[self._index]
        self._index += 1
        return token

    def peek_value(self, value: str) -> bool:
        token = self.peek()
        return token[1] == value

    def expect(self, value: str) -> None:
        token = self.next()
        if token[1] != value:
            raise ValueError(f"Expected '{value}' but found '{token[1]}'")


def _parse_expression(stream: _TokenStream) -> int:
    return _parse_ternary(stream)


def _parse_ternary(stream: _TokenStream) -> int:
    value = _parse_logical_or(stream)
    if stream.peek_value('?'):
        stream.next()
        true_value = _parse_ternary(stream)
        stream.expect(':')
        false_value = _parse_ternary(stream)
        return true_value if value != 0 else false_value
    return value


def _parse_logical_or(stream: _TokenStream) -> int:
    value = _parse_logical_and(stream)
    while stream.peek_value('||'):
        stream.next()
        right = _parse_logical_and(stream)
        value = 1 if (value != 0 or right != 0) else 0
    return value


def _parse_logical_and(stream: _TokenStream) -> int:
    value = _parse_bitwise_or(stream)
    while stream.peek_value('&&'):
        stream.next()
        right = _parse_bitwise_or(stream)
        value = 1 if (value != 0 and right != 0) else 0
    return value


def _parse_bitwise_or(stream: _TokenStream) -> int:
    value = _parse_bitwise_xor(stream)
    while stream.peek_value('|'):
        stream.next()
        right = _parse_bitwise_xor(stream)
        value = value | right
    return value


def _parse_bitwise_xor(stream: _TokenStream) -> int:
    value = _parse_bitwise_and(stream)
    while stream.peek_value('^'):
        stream.next()
        right = _parse_bitwise_and(stream)
        value = value ^ right
    return value


def _parse_bitwise_and(stream: _TokenStream) -> int:
    value = _parse_equality(stream)
    while stream.peek_value('&'):
        stream.next()
        right = _parse_equality(stream)
        value = value & right
    return value


def _parse_equality(stream: _TokenStream) -> int:
    value = _parse_relational(stream)
    while stream.peek()[1] in {'==', '!='}:
        op = stream.next()[1]
        right = _parse_relational(stream)
        if op == '==':
            value = 1 if value == right else 0
        else:
            value = 1 if value != right else 0
    return value


def _parse_relational(stream: _TokenStream) -> int:
    value = _parse_shift(stream)
    while stream.peek()[1] in {'<', '>', '<=', '>='}:
        op = stream.next()[1]
        right = _parse_shift(stream)
        if op == '<':
            value = 1 if value < right else 0
        elif op == '>':
            value = 1 if value > right else 0
        elif op == '<=':
            value = 1 if value <= right else 0
        else:
            value = 1 if value >= right else 0
    return value


def _parse_shift(stream: _TokenStream) -> int:
    value = _parse_additive(stream)
    while stream.peek()[1] in {'<<', '>>'}:
        op = stream.next()[1]
        right = _parse_additive(stream)
        if op == '<<':
            value = value << right
        else:
            value = value >> right
    return value


def _parse_additive(stream: _TokenStream) -> int:
    value = _parse_multiplicative(stream)
    while stream.peek()[1] in {'+', '-'}:
        op = stream.next()[1]
        right = _parse_multiplicative(stream)
        if op == '+':
            value = value + right
        else:
            value = value - right
    return value


def _parse_multiplicative(stream: _TokenStream) -> int:
    value = _parse_unary(stream)
    while stream.peek()[1] in {'*', '/', '%'}:
        op = stream.next()[1]
        right = _parse_unary(stream)
        if op == '*':
            value = value * right
        elif op == '/':
            if right == 0:
                raise ValueError("Division by zero in expression")
            value = int(value / right)
        else:
            if right == 0:
                raise ValueError("Modulo by zero in expression")
            value = value % right
    return value


def _parse_unary(stream: _TokenStream) -> int:
    token = stream.peek()
    if token[1] in {'+', '-', '!', '~'}:
        op = stream.next()[1]
        operand = _parse_unary(stream)
        if op == '+':
            return +operand
        if op == '-':
            return -operand
        if op == '!':
            return 0 if operand else 1
        return ~operand
    return _parse_primary(stream)


def _parse_primary(stream: _TokenStream) -> int:
    token = stream.peek()
    if token[1] == '(':
        stream.next()
        value = _parse_expression(stream)
        stream.expect(')')
        return value
    if token[0] == 'NUMBER':
        stream.next()
        return int(token[1])
    raise ValueError(f"Unexpected token in expression: {token}")


def _evaluate_numeric(expr: str) -> int:
    text = expr.strip()
    if not text:
        return 0
    tokens = _tokenize_expression(text)
    stream = _TokenStream(tokens)
    value = _parse_expression(stream)
    return int(value)


def _parse_evolutions(value: str) -> List[Tuple[str, str, str, List[str]]]:
    if not value:
        return []
    text = value.strip()
    if text == 'EVOLUTION(NULL)':
        return []
    if text.startswith('EVOLUTION'):
        start = text.find('(')
        end = text.rfind(')')
        if start != -1 and end != -1:
            text = text[start + 1 : end]
    entries: List[Tuple[str, str, str, List[str]]] = []
    current: List[str] = []
    brace_depth = 0
    for char in text:
        if char == '{':
            if brace_depth == 0:
                current = []
            brace_depth += 1
        if brace_depth > 0:
            current.append(char)
        if char == '}':
            brace_depth -= 1
            if brace_depth == 0:
                entry_text = ''.join(current).strip()
                if entry_text.startswith('{') and entry_text.endswith('}'):
                    entry_text = entry_text[1:-1]
                parts = [part.strip() for part in _split_top_level(entry_text) if part.strip()]
                if len(parts) < 3:
                    continue
                method, parameter, target, *rest = parts
                conditions: List[str] = []
                for extra in rest:
                    if extra.startswith('CONDITIONS'):
                        start = extra.find('(')
                        end = extra.rfind(')')
                        if start == -1 or end == -1:
                            continue
                        condition_block = extra[start + 1 : end]
                        inner_entries: List[str] = []
                        depth = 0
                        start_idx: Optional[int] = None
                        for idx, token in enumerate(condition_block):
                            if token == '{':
                                if depth == 0:
                                    start_idx = idx + 1
                                depth += 1
                            elif token == '}':
                                depth -= 1
                                if depth == 0 and start_idx is not None:
                                    inner_entries.append(condition_block[start_idx:idx])
                                    start_idx = None
                        for condition in inner_entries:
                            cond_parts = [part.strip() for part in _split_top_level(condition) if part.strip()]
                            if cond_parts:
                                conditions.append(' '.join(cond_parts))
                    else:
                        conditions.append(extra)
                entries.append((method, parameter, target, conditions))
    return entries


def _parse_level_up_learnsets(header: Path) -> Dict[str, List[LearnsetEntry]]:
    directory = project_paths.REPO_ROOT / "src" / "data" / "pokemon" / "level_up_learnsets"
    array_pattern = r"static const struct LevelUpMove\s+(?P<name>\w+)\[\]\s*=\s*\{(?P<body>.*?)\};"
    move_pattern = re.compile(r"\.move\s*=\s*([^,]+),\s*\.level\s*=\s*([^,}]+)")
    macro_pattern = re.compile(r"LEVEL_UP_MOVE\s*\(([^,]+),\s*([^\)]+)\)")
    learnsets: Dict[str, List[LearnsetEntry]] = {}
    for path in sorted(directory.glob("*.h")):
        text = _run_cpp(path, header)
        for match in re.finditer(array_pattern, text, re.DOTALL):
            name = match.group('name')
            body = match.group('body')
            entries: List[LearnsetEntry] = []
            for move_match in move_pattern.finditer(body):
                move = move_match.group(1).strip()
                level_text = move_match.group(2).strip()
                if move in {"MOVE_UNAVAILABLE", "LEVEL_UP_MOVE_END"} or move.startswith("0x"):
                    continue
                if move == "MOVE_NONE":
                    continue
                level = _evaluate_numeric(level_text)
                entries.append(LearnsetEntry(level=level, move=move))
            if not entries:
                for move_match in macro_pattern.finditer(body):
                    level_text = move_match.group(1).strip()
                    move = move_match.group(2).strip()
                    if move in {"MOVE_UNAVAILABLE", "LEVEL_UP_MOVE_END", "MOVE_NONE"}:
                        continue
                    level = _evaluate_numeric(level_text)
                    entries.append(LearnsetEntry(level=level, move=move))
            learnsets[name] = entries
    return learnsets


def _parse_move_learnsets(path: Path, header: Path) -> Dict[str, List[str]]:
    text = _run_cpp(path, header)
    array_pattern = re.compile(
        r"static const u16\\s+(?P<name>\\w+)\\[\\]\\s*=\\s*\\{(?P<body>.*?)\\};",
        re.DOTALL,
    )
    learnsets: Dict[str, List[str]] = {}
    for match in array_pattern.finditer(text):
        name = match.group('name')
        body = match.group('body')
        moves: List[str] = []
        for token in body.replace('\n', ' ').split(','):
            entry = token.strip()
            if not entry or entry in {"MOVE_UNAVAILABLE", "MOVE_NONE"}:
                continue
            moves.append(entry)
        learnsets[name] = moves
    return learnsets


def _build_ev_yield(assignments: Dict[str, str]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for field, key in EV_YIELD_FIELDS:
        if field in assignments:
            value = _evaluate_numeric(assignments[field])
            if value:
                result[key] = value
    return result


def _ensure_two_types(types: List[str]) -> List[str]:
    if not types:
        return ["TYPE_NORMAL", "TYPE_NORMAL"]
    if len(types) == 1:
        return [types[0], types[0]]
    return types[:2]


def _ensure_two_egg_groups(groups: List[str]) -> List[str]:
    if not groups:
        return ["EGG_GROUP_NO_EGGS_DISCOVERED", "EGG_GROUP_NO_EGGS_DISCOVERED"]
    if len(groups) == 1:
        return [groups[0], groups[0]]
    return groups[:2]


def populate_database(database: PokemonDatabase) -> None:
    _ = load_species_metadata()  # Ensures data dependencies are generated if necessary.
    species_list = _collect_enabled_species()
    family_map = _species_family_mapping()

    with tempfile.TemporaryDirectory() as temp_dir:
        header_path = Path(temp_dir) / "preproc_config.h"
        header_path.write_text(PREPROC_HEADER, encoding="utf-8")

        species_info: Dict[str, Dict[str, str]] = {}
        for path in sorted(project_paths.SPECIES_INFO_DIR.glob("*_families.h")):
            text = _run_cpp(path, header_path)
            species_info.update(_parse_species_info_text(text))

        custom_species_info = _load_custom_species_info(header_path)
        if custom_species_info:
            species_info.update(custom_species_info)
            for custom_species in custom_species_info:
                if custom_species not in species_list:
                    species_list.append(custom_species)

        level_up_learnsets = _parse_level_up_learnsets(header_path)
        egg_move_learnsets = _parse_move_learnsets(
            project_paths.REPO_ROOT / "src" / "data" / "pokemon" / "egg_moves.h",
            header_path,
        )
        teachable_learnsets = _parse_move_learnsets(
            project_paths.REPO_ROOT / "src" / "data" / "pokemon" / "teachable_learnsets.h",
            header_path,
        )

        for species in species_list:
            info = species_info.get(species)
            if info is None:
                continue

            family_macro = family_map.get(species, species.replace("SPECIES_", "P_FAMILY_"))
            display_name = _extract_string(info.get("speciesName", species))
            category_name = _extract_string(info.get("categoryName", ""))
            description = _parse_compound_string(info.get("description", ""))
            height = _evaluate_numeric(info.get("height", "0"))
            weight = _evaluate_numeric(info.get("weight", "0"))

            types = _ensure_two_types(_parse_macro_arguments(info.get("types", "")))
            abilities = _parse_braced_list(info.get("abilities", "")) or ["ABILITY_NONE"]
            catch_rate = _evaluate_numeric(info.get("catchRate", "0"))
            exp_yield = _evaluate_numeric(info.get("expYield", "0"))
            growth_rate = info.get("growthRate", "GROWTH_MEDIUM_FAST").strip() or "GROWTH_MEDIUM_FAST"
            egg_groups = _ensure_two_egg_groups(_parse_macro_arguments(info.get("eggGroups", "")))
            gender_ratio = info.get("genderRatio", "MON_GENDERLESS").strip() or "MON_GENDERLESS"
            egg_cycles = _evaluate_numeric(info.get("eggCycles", "0"))
            friendship = str(_evaluate_numeric(info.get("friendship", "0")))

            base_stats = {
                "hp": _evaluate_numeric(info.get("baseHP", "0")),
                "attack": _evaluate_numeric(info.get("baseAttack", "0")),
                "defense": _evaluate_numeric(info.get("baseDefense", "0")),
                "speed": _evaluate_numeric(info.get("baseSpeed", "0")),
                "spAttack": _evaluate_numeric(info.get("baseSpAttack", "0")),
                "spDefense": _evaluate_numeric(info.get("baseSpDefense", "0")),
            }
            ev_yield = _build_ev_yield(info)

            level_key = info.get("levelUpLearnset", "").strip()
            level_moves = level_up_learnsets.get(level_key, [])
            egg_key = info.get("eggMoveLearnset", "").strip()
            egg_moves = egg_move_learnsets.get(egg_key, [])
            teachable_key = info.get("teachableLearnset", "").strip()
            teachable_moves = teachable_learnsets.get(teachable_key, [])

            evolutions = [
                EvolutionEntry(
                    from_species=species,
                    method=method,
                    parameter=parameter,
                    target_species=target,
                    conditions=conditions,
                )
                for method, parameter, target, conditions in _parse_evolutions(info.get("evolutions", ""))
            ]

            natdex = info.get("natDexNum")
            if natdex:
                natdex = natdex.strip()
            else:
                natdex = f"NATIONAL_DEX_{species.replace('SPECIES_', '')}"

            cry = info.get("cryId", "CRY_NONE").strip() or "CRY_NONE"
            icon_value: Optional[int] = None
            icon_expr = info.get("iconPalIndex")
            if icon_expr:
                try:
                    icon_value = _evaluate_numeric(icon_expr)
                except ValueError:
                    icon_value = None

            folder = showdown_folder_from_species(species)
            assets = _build_asset_bundle(folder)
            if assets is None:
                print(f"Skipping {species} because required graphics assets are missing.")
                continue

            pokemon = PokemonData(
                species_constant=species,
                family_macro=family_macro,
                national_dex_constant=natdex,
                display_name=display_name,
                category_name=category_name,
                description=description,
                height=height,
                weight=weight,
                types=types,
                abilities=abilities,
                catch_rate=catch_rate,
                exp_yield=exp_yield,
                growth_rate=growth_rate,
                egg_groups=egg_groups,
                gender_ratio=gender_ratio,
                egg_cycles=egg_cycles,
                friendship=friendship,
                base_stats=base_stats,
                ev_yield=ev_yield,
                learnset_level_up=level_moves,
                learnset_egg=egg_moves,
                learnset_tm=teachable_moves,
                evolutions=evolutions,
                dex_order_hint={"height": height, "weight": weight},
                cry=cry,
                graphics_folder=folder,
                icon_pal_index=icon_value,
            )
            database.save_entry(pokemon, assets)


def main() -> None:
    project_paths.ensure_directories()
    database = PokemonDatabase()
    populate_database(database)


if __name__ == "__main__":
    main()
