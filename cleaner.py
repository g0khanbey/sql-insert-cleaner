from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import os
import re
import tempfile
from typing import Callable, Iterable, Optional, TextIO


INSERT_PATTERN = re.compile(
    r"^INSERT\s+(?:(?:LOW_PRIORITY|DELAYED|HIGH_PRIORITY|IGNORE)\s+)*"
    r"INTO\s+(?P<table>"
    r"(?:`(?:``|[^`])+`|\"(?:\"\"|[^\"])+\"|\[(?:\]\]|[^\]])+\]|[\w$-]+)"
    r"(?:\s*\.\s*(?:`(?:``|[^`])+`|\"(?:\"\"|[^\"])+\"|"
    r"\[(?:\]\]|[^\]])+\]|[\w$-]+))*"
    r")",
    re.IGNORECASE | re.UNICODE,
)


@dataclass(frozen=True)
class CleanResult:
    output_path: Path
    removed_statements: int
    removed_by_table: dict[str, int]
    source_size: int
    output_size: int


def iter_sql_statements(stream: TextIO, chunk_size: int = 65536) -> Iterable[str]:
    buffer: list[str] = []
    mode: Optional[str] = None
    escaped = False
    previous = ""

    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            break

        for character in chunk:
            buffer.append(character)

            if mode in ("'", '"', "`"):
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == mode:
                    mode = None
                previous = character
                continue

            if mode == "line_comment":
                if character in ("\n", "\r"):
                    mode = None
                previous = character
                continue

            if mode == "block_comment":
                if previous == "*" and character == "/":
                    mode = None
                previous = character
                continue

            if previous == "-" and character == "-":
                mode = "line_comment"
            elif character == "#":
                mode = "line_comment"
            elif previous == "/" and character == "*":
                mode = "block_comment"
            elif character in ("'", '"', "`"):
                mode = character
            elif character == ";":
                yield "".join(buffer)
                buffer.clear()
                previous = ""
                continue

            previous = character

    if buffer:
        yield "".join(buffer)


def split_leading_prefix(statement: str) -> tuple[str, str]:
    position = 0
    length = len(statement)

    while position < length:
        start = position

        while position < length and (statement[position].isspace() or statement[position] == "\ufeff"):
            position += 1

        if statement.startswith("--", position) or statement.startswith("#", position):
            newline = statement.find("\n", position)
            position = length if newline == -1 else newline + 1
            continue

        if statement.startswith("/*", position):
            end = statement.find("*/", position + 2)
            if end == -1:
                return statement, ""
            position = end + 2
            continue

        if position == start:
            break

    return statement[:position], statement[position:]


def normalize_identifier(identifier: str) -> str:
    parts = re.findall(
        r"`(?:``|[^`])+`|\"(?:\"\"|[^\"])+\"|\[(?:\]\]|[^\]])+\]|[\w$-]+",
        identifier,
        re.UNICODE,
    )
    normalized = []

    for part in parts:
        if part.startswith("`"):
            normalized.append(part[1:-1].replace("``", "`"))
        elif part.startswith('"'):
            normalized.append(part[1:-1].replace('""', '"'))
        elif part.startswith("["):
            normalized.append(part[1:-1].replace("]]", "]"))
        else:
            normalized.append(part)

    return ".".join(normalized)


def extract_insert_table(statement: str) -> Optional[str]:
    _, body = split_leading_prefix(statement)
    match = INSERT_PATTERN.match(body)
    if not match:
        return None
    return normalize_identifier(match.group("table"))


def scan_insert_tables(source_path: str | Path) -> OrderedDict[str, int]:
    source = Path(source_path)
    counts: OrderedDict[str, int] = OrderedDict()

    with source.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
        for statement in iter_sql_statements(stream):
            table = extract_insert_table(statement)
            if table:
                counts[table] = counts.get(table, 0) + 1

    return counts


def clean_sql_file(
    source_path: str | Path,
    output_path: str | Path,
    selected_tables: Optional[set[str]] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> CleanResult:
    source = Path(source_path).resolve()
    output = Path(output_path).resolve()

    if source == output:
        raise ValueError("Kaynak dosya ile çıktı dosyası aynı olamaz.")

    if not source.is_file():
        raise FileNotFoundError(f"SQL dosyası bulunamadı: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    removed_by_table: OrderedDict[str, int] = OrderedDict()
    processed = 0
    last_progress = -1
    source_size = source.stat().st_size

    temporary = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary_path = Path(temporary.name)

    try:
        with source.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream, temporary:
            for statement in iter_sql_statements(stream):
                prefix, body = split_leading_prefix(statement)
                table = extract_insert_table(statement)

                if table and (selected_tables is None or table in selected_tables):
                    temporary.write(prefix)
                    removed_by_table[table] = removed_by_table.get(table, 0) + 1
                else:
                    temporary.write(prefix)
                    temporary.write(body)

                processed += len(statement.encode("utf-8", errors="replace"))
                if progress_callback and source_size:
                    progress = min(100, int(processed * 100 / source_size))
                    if progress != last_progress:
                        progress_callback(progress)
                        last_progress = progress

        os.replace(temporary_path, output)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    if progress_callback:
        progress_callback(100)

    return CleanResult(
        output_path=output,
        removed_statements=sum(removed_by_table.values()),
        removed_by_table=dict(removed_by_table),
        source_size=source_size,
        output_size=output.stat().st_size,
    )
