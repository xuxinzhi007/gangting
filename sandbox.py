"""Read and patch a Project Zomboid SandboxVars.lua without rewriting the rest."""

import math
import re

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OPTION = re.compile(r"^(\d+(?:\.\d+)?)\s*=\s*(.+)$")


def parse_sandbox(text):
    fields = []
    stack = []
    comments = []
    for index, line in enumerate(text.splitlines()):
        raw = line.strip()
        if not raw:
            continue
        if raw.startswith("--"):
            comments.append(raw[2:].strip())
            continue
        if raw in ("SandboxVars = {", "{"):
            comments = []
            continue
        if raw.startswith("}"):
            if stack:
                stack.pop()
            comments = []
            continue
        if "=" not in raw:
            comments = []
            continue
        name, _, literal = raw.partition("=")
        name = name.strip()
        literal = literal.strip()
        if literal.endswith(","):
            literal = literal[:-1].rstrip()
        if not _NAME.match(name):
            comments = []
            continue
        if literal == "{":
            stack.append(name)
            comments = []
            continue
        kind, value = _decode(literal)
        if kind is None:
            comments = []
            continue
        options = []
        prose = []
        for comment in comments:
            option = _OPTION.match(comment)
            if option:
                options.append({"value": option.group(1), "label": option.group(2).strip()})
            else:
                prose.append(comment)
        fields.append({
            "path": ".".join([*stack, name]),
            "name": name,
            "group": stack[0] if stack else "",
            "line": index,
            "kind": kind,
            "value": value,
            "comment": " ".join(prose),
            "options": options,
        })
        comments = []
    return fields


def apply_sandbox(text, updates):
    if not isinstance(updates, dict) or not updates:
        raise ValueError("没有要写入的沙盒项")
    by_path = {item["path"]: item for item in parse_sandbox(text)}
    lines = text.splitlines()
    changed = []
    for path, raw in updates.items():
        field = by_path.get(str(path))
        if field is None:
            raise ValueError("没有这个沙盒项")
        if field["name"] == "VERSION":
            raise ValueError("沙盒版本号不能改")
        literal = encode_value(field, raw)
        current = encode_value(field, field["value"])
        if literal == current:
            continue
        original = lines[field["line"]]
        comma = "," if original.rstrip().endswith(",") else ""
        prefix = original.split("=", 1)[0]
        lines[field["line"]] = f"{prefix}= {literal}{comma}"
        changed.append(field["path"])
    separator = "\r\n" if "\r\n" in text else "\n"
    rewritten = separator.join(lines)
    if text.endswith(("\n", "\r\n")):
        rewritten += separator
    return rewritten, changed


def encode_value(field, raw):
    kind = field["kind"]
    options = {item["value"] for item in field["options"]}
    if kind == "bool":
        if isinstance(raw, bool):
            return "true" if raw else "false"
        text = str(raw).strip().lower()
        if text not in ("true", "false"):
            raise ValueError(f"{field['name']}只能是 true 或 false")
        return text
    if kind == "string":
        text = str(raw)
        if not text or len(text) > 80 or any(char in text for char in '"\\\r\n'):
            raise ValueError(f"{field['name']}的文字不对")
        return f'"{text}"'
    number = _number(field["name"], raw, integer=kind == "int")
    rendered = str(number) if kind == "int" else _float_text(number)
    if options and rendered not in options and str(raw).strip() not in options:
        raise ValueError(f"{field['name']}不在文件给出的选项里")
    if options and str(raw).strip() in options and kind == "int":
        return str(int(str(raw).strip()))
    return rendered


def _decode(literal):
    if literal in ("true", "false"):
        return "bool", literal == "true"
    if len(literal) >= 2 and literal[0] == '"' and literal[-1] == '"':
        return "string", literal[1:-1]
    if re.fullmatch(r"-?\d+", literal):
        return "int", int(literal)
    if re.fullmatch(r"-?\d+\.\d+", literal):
        return "float", float(literal)
    return None, None


def _number(name, raw, integer):
    try:
        number = int(str(raw).strip()) if integer else float(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}要填数字") from exc
    if isinstance(number, float) and not math.isfinite(number):
        raise ValueError(f"{name}要填数字")
    if abs(number) > 1000000:
        raise ValueError(f"{name}超出范围")
    return number


def _float_text(number):
    text = f"{float(number):.6f}".rstrip("0").rstrip(".")
    if "." not in text:
        text += ".0"
    return text
