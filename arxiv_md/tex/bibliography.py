from __future__ import annotations

import re
from pathlib import Path

from arxiv_md.tex._common import BibEntry, ResourceLimits, TexWarning, warning


def parse_bibliography(
    root_dir: Path,
    source_text: str,
    warnings: list[TexWarning],
    *,
    limits: ResourceLimits | None = None,
) -> list[BibEntry]:
    entries = _parse_thebibliography(source_text)
    if entries:
        return entries

    caps = limits or ResourceLimits()
    state = _ScanState(
        cap=caps.max_bib_files_scanned, max_bytes=caps.max_single_file_bytes
    )

    for bbl in sorted(root_dir.rglob("*.bbl")):
        if state.cap_reached(bbl, warnings):
            break
        state.scanned += 1
        if not state.size_ok(bbl, warnings):
            continue
        try:
            entries = _parse_thebibliography(
                bbl.read_text(encoding="utf-8", errors="ignore")
            )
        except OSError:
            continue
        if entries:
            return entries

    bib_entries: list[BibEntry] = []
    for bib in sorted(root_dir.rglob("*.bib")):
        if state.cap_reached(bib, warnings):
            break
        state.scanned += 1
        if not state.size_ok(bib, warnings):
            continue
        try:
            bib_entries.extend(
                _parse_bib(bib.read_text(encoding="utf-8", errors="ignore"))
            )
        except OSError:
            warnings.append(
                warning("bib_parse_partial", f"Could not read bibliography: {bib}", bib)
            )
    return bib_entries


class _ScanState:
    __slots__ = ("cap", "max_bytes", "scanned", "_cap_warned")

    def __init__(self, cap: int, max_bytes: int) -> None:
        self.cap = cap
        self.max_bytes = max_bytes
        self.scanned = 0
        self._cap_warned = False

    def cap_reached(self, path: Path, warnings: list[TexWarning]) -> bool:
        if self.scanned < self.cap:
            return False
        if not self._cap_warned:
            warnings.append(
                warning(
                    "resource_limit",
                    f"Bibliography scan stopped at max_bib_files_scanned={self.cap}; "
                    f"remaining .bbl/.bib files ignored starting with {path}",
                    path,
                )
            )
            self._cap_warned = True
        return True

    def size_ok(self, path: Path, warnings: list[TexWarning]) -> bool:
        try:
            size = path.stat().st_size
        except OSError:
            return True
        if size > self.max_bytes:
            warnings.append(
                warning(
                    "resource_limit",
                    f"Bibliography file skipped: {path} size={size} exceeds "
                    f"max_single_file_bytes={self.max_bytes}",
                    path,
                )
            )
            return False
        return True


# BibTeX line-trailing % comments can split \bibitem[...]%\n from {key},
# so allow a `]`-terminated optional label, then any amount of whitespace /
# % comment lines before the mandatory {key} group.
_BIBITEM_RE = re.compile(
    r"\\bibitem(?:\[[^\]]*\])?(?:\s*%[^\n]*\n)*\s*\{([^{}]+)\}(.*)",
    re.S,
)


# Real bibliography entry types only. @String/@preamble/@comment are macro
# definitions, not citations; matching them pollutes the reference list.
_ENTRY_TYPES: str = (
    "article|inproceedings|conference|book|incollection|inbook|booklet|"
    "proceedings|collection|phdthesis|mastersthesis|techreport|manual|misc|"
    "unpublished|online|electronic|www|patent|dataset"
)
_ENTRY_BODY_RE = re.compile(r"([^,{}=]+),(.*?)\n\}", re.S)


def _parse_thebibliography(text: str) -> list[BibEntry]:
    env = re.search(
        r"\\begin\{thebibliography\}(?:\{[^{}]*\})?(.*?)\\end\{thebibliography\}",
        text,
        re.S,
    )
    if not env:
        return []
    body = env.group(1)
    chunks = re.split(r"(?=\\bibitem)", body)
    entries: list[BibEntry] = []
    for chunk in chunks:
        match = _BIBITEM_RE.match(chunk.strip())
        if not match:
            continue
        key = match.group(1).strip()
        value = _clean_latex_text(_strip_bbl_markup(match.group(2)))
        entries.append(BibEntry(key=key, text=value))
    return entries


def _strip_bbl_markup(text: str) -> str:
    """Strip BibTeX style markup that is not user-visible prose.

    ACM-Reference-Format .bbl files wrap fields in \\bibfield{...}{...} and
    \\bibinfo{kind}{...} and sprinkle \\natexlab / \\newblock / \\showeprint.
    The wrapper names (author, person, year, ...) must not leak into the
    rendered reference text. \\bibinfo content may itself contain balanced
    braces (e.g. ``{ACM} Transactions''), so strip inner \\bibinfo first,
    then outer \\bibfield.
    """
    text = re.sub(r"\\bibinfo\{[^{}]*\}\{(.*?)\}", r"\1", text, flags=re.S)
    text = re.sub(r"\\bibfield\{[^{}]*\}\{(.*?)\}", r"\1", text, flags=re.S)
    text = re.sub(r"\\natexlab\{[^{}]*\}", "", text)
    text = re.sub(r"\\newblock", " ", text)
    return text


def _parse_bib(text: str) -> list[BibEntry]:
    entries: list[BibEntry] = []
    entry_start = re.compile(rf"@\s*({_ENTRY_TYPES})\s*{{", re.I)
    for type_match in entry_start.finditer(text):
        key, body = _read_bib_entry(text, type_match.end())
        if key is None:
            continue
        title = _field(body, "title")
        author = _field(body, "author")
        year = _field(body, "year")
        pieces = [piece for piece in (author, title, year) if piece]
        entries.append(BibEntry(key=key, text=". ".join(pieces)))
    return entries


def _read_bib_entry(text: str, start: int) -> tuple[str | None, str]:
    """Parse `{key, body}` starting at `start` (just after `@type{`)."""
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                break
            depth -= 1
        i += 1
    raw = text[start:i]
    # Split at the first top-level comma after the key.
    depth = 0
    for j, ch in enumerate(raw):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            key = raw[:j].strip().strip("\\")
            return (key or None), raw[j + 1 :]
    return None, raw


def _field(body: str, name: str) -> str:
    match = re.search(name + r"\s*=\s*[\{\"](.*?)[\}\"]\s*,", body, re.I | re.S)
    if not match:
        return ""
    return _clean_latex_text(match.group(1))


def _clean_latex_text(text: str) -> str:

    from arxiv_md.tex.lexer import Diagnostics
    from arxiv_md.tex.parser import parse_text
    from arxiv_md.tex.transform.context import TransformContext
    from arxiv_md.tex.transform.inline_render import InlineSerializer

    diag = Diagnostics()
    nodes = parse_text(text, diag)
    ctx = TransformContext(
        diag=diag,
        source_text=text,
        macros={},
        inline_serializer=InlineSerializer(ref_style="bracket"),
    )
    return ctx.inline_markdown(nodes)
