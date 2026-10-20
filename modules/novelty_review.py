"""Keep automatic candidates separate from explicitly edited review evidence."""
from dataclasses import replace

from modules.novelty_models import EvidenceRow, Feature


def empty_review_rows(features: list[Feature]) -> tuple[EvidenceRow, ...]:
    return tuple(EvidenceRow(f.id, basis="", origin="human") for f in features)


def adopt_candidate_quotes(rows: tuple[EvidenceRow, ...], candidates: tuple[EvidenceRow, ...],
                           selected_ids: list[str]) -> tuple[EvidenceRow, ...]:
    candidates_by_id = {row.feature_id: row for row in candidates}
    result = []
    for row in rows:
        candidate = candidates_by_id.get(row.feature_id)
        if row.feature_id in selected_ids and candidate and candidate.quote.strip():
            row = replace(row, section_id=candidate.section_id, quote=candidate.quote,
                          status="unknown", scheme_id="", basis="", origin=candidate.origin)
        result.append(row)
    return tuple(result)


def edited_review_rows(edited: list[dict], baseline: tuple[EvidenceRow, ...]) -> tuple[EvidenceRow, ...]:
    previous = {row.feature_id: row for row in baseline}
    result = []
    for value in edited:
        row = EvidenceRow(**value)
        old = previous.get(row.feature_id)
        if old:
            if row.quote != old.quote or row.section_id != old.section_id:
                row = replace(row, origin="human")
            changed = any(getattr(row, key) != getattr(old, key)
                          for key in ("status", "quote", "section_id", "scheme_id"))
            if changed and row.basis == old.basis:
                row = replace(row, basis="")  # The old explanation cannot silently describe a new status.
        result.append(row)
    return tuple(result)
