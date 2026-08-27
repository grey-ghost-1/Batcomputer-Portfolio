"""Curated, bounded website knowledge index.

Knowledge is built only from a fixed allow-list of safe repository sources:
``README.md`` and ``project-evidence.json`` at the knowledge root. Content is
treated strictly as data: any instructions embedded in indexed text are ignored,
never obeyed. The index cites repo-relative source paths and never performs
arbitrary file reads driven by user input.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Fixed allow-list of curated sources (repo-relative). Nothing else is read.
README_SOURCE = "README.md"
EVIDENCE_SOURCE = "project-evidence.json"

PRIMARY_CASE_STUDIES = {
    "operations-platform",
    "orbital-data-lab",
    "algorithm-quality-lab",
}

CATEGORY_NAMES = (
    "Software Development",
    "Cybersecurity",
    "IT Support",
    "Network",
    "Software Automation",
)

# Patterns commonly used in prompt-injection attempts. Matching lines are marked
# as neutralised data rather than removed, so citations stay honest.
_INJECTION_PATTERNS = re.compile(
    r"(ignore (all )?(previous|prior|above) instructions"
    r"|disregard (the )?(above|previous)"
    r"|system prompt"
    r"|reveal (the )?(secret|token|password)"
    r"|exfiltrate"
    r"|run (the )?following (command|shell)"
    r"|execute .* (command|shell|powershell)"
    r"|delete .* file)",
    re.IGNORECASE,
)

_WORD = re.compile(r"[a-z0-9]+")


def sanitize_snippet(text: str, *, limit: int = 320) -> str:
    """Collapse whitespace, bound length, and neutralise injection phrases."""

    collapsed = " ".join(text.split())
    if _INJECTION_PATTERNS.search(collapsed):
        collapsed = _INJECTION_PATTERNS.sub("[neutralised instruction]", collapsed)
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 1].rstrip() + "\u2026"
    return collapsed


def _tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


@dataclass
class Document:
    doc_id: str
    title: str
    source_path: str
    text: str
    tokens: set[str] = field(default_factory=set)

    def snippet(self) -> str:
        return sanitize_snippet(self.text)


@dataclass
class Citation:
    title: str
    source_path: str
    snippet: str


class KnowledgeIndex:
    """A small in-memory index over the curated sources."""

    def __init__(self, documents: list[Document], *, sources: list[str], truncated: bool) -> None:
        self.documents = documents
        self.sources = sources
        self.truncated = truncated

    @property
    def document_count(self) -> int:
        return len(self.documents)

    def status(self) -> dict:
        return {
            "document_count": self.document_count,
            "sources": list(self.sources),
            "primary_case_studies": sorted(PRIMARY_CASE_STUDIES),
            "categories": list(CATEGORY_NAMES),
            "truncated": self.truncated,
            "injection_defense": "indexed content is treated as data and never executed",
        }

    def search(self, query: str, *, limit: int = 3) -> list[Citation]:
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return []
        scored: list[tuple[float, Document]] = []
        for document in self.documents:
            overlap = query_tokens & document.tokens
            if not overlap:
                continue
            score = len(overlap) + sum(
                0.25 for token in query_tokens if token in document.title.lower()
            )
            scored.append((score, document))
        scored.sort(key=lambda item: (-item[0], item[1].doc_id))
        return [
            Citation(title=doc.title, source_path=doc.source_path, snippet=doc.snippet())
            for _, doc in scored[:limit]
        ]


def _read_readme(root: Path, max_bytes: int) -> tuple[list[Document], bool]:
    path = root / README_SOURCE
    if not path.is_file():
        return [], False
    raw = path.read_bytes()
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8", errors="ignore")
    documents: list[Document] = []
    current_title = "README"
    buffer: list[str] = []
    order = 0

    def flush() -> None:
        nonlocal order
        body = "\n".join(buffer).strip()
        if body:
            documents.append(
                Document(
                    doc_id=f"readme-{order}",
                    title=f"README \u203a {current_title}",
                    source_path=README_SOURCE,
                    text=body,
                )
            )
            order += 1

    for line in text.splitlines():
        heading = re.match(r"^#{1,6}\s+(.*)$", line)
        if heading:
            flush()
            buffer = []
            current_title = heading.group(1).strip() or "Section"
        else:
            buffer.append(line)
    flush()
    return documents, truncated


def _read_evidence(root: Path) -> list[Document]:
    path = root / EVIDENCE_SOURCE
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    documents: list[Document] = []

    summary_bits = [
        f"Repository {data.get('repository', 'unknown')}",
        f"Project count {data.get('project_count', 'unknown')}",
        str(data.get("validation_summary", "")),
    ]
    documents.append(
        Document(
            doc_id="evidence-summary",
            title="Portfolio evidence summary",
            source_path=EVIDENCE_SOURCE,
            text=" ".join(bit for bit in summary_bits if bit),
        )
    )

    for project in data.get("projects", []):
        if not isinstance(project, dict):
            continue
        slug = str(project.get("slug", "")).strip()
        if not slug:
            continue
        features = ", ".join(str(item) for item in project.get("implemented_features", []))
        limitations = ", ".join(str(item) for item in project.get("limitations", []))
        body = (
            f"Project {slug}. Source folder {project.get('source_folder', 'unknown')}. "
            f"Implemented features: {features or 'not listed'}. "
            f"Limitations: {limitations or 'not listed'}. "
            f"Validation status: {project.get('validation_status', 'unknown')}."
        )
        title = slug
        if slug in PRIMARY_CASE_STUDIES:
            title = f"Primary case study: {slug}"
        documents.append(
            Document(
                doc_id=f"evidence-{slug}",
                title=title,
                source_path=EVIDENCE_SOURCE,
                text=body,
            )
        )
    return documents


def build_index(root: Path, *, max_bytes: int = 512 * 1024) -> KnowledgeIndex:
    root = Path(root)
    readme_docs, truncated = _read_readme(root, max_bytes)
    evidence_docs = _read_evidence(root)
    documents = readme_docs + evidence_docs
    for document in documents:
        document.tokens = set(_tokenize(f"{document.title} {document.text}"))
    sources = sorted({document.source_path for document in documents})
    return KnowledgeIndex(documents, sources=sources, truncated=truncated)
