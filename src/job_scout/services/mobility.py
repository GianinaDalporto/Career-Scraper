"""Visa, relocation, citizenship and professional-registration flags."""

from __future__ import annotations

import re

from job_scout.models.job import MobilityFlags, RawJobRecord


def extract_mobility(title: str, description: str, raw: RawJobRecord) -> MobilityFlags:
    blob = f"{title}\n{description}".lower()
    flags = MobilityFlags(
        visa_sponsorship=raw.visa_sponsorship,
        relocation_assistance=raw.relocation_assistance,
        unknown=True,
    )
    notes: list[str] = []

    if flags.visa_sponsorship is None:
        if re.search(
            r"visa sponsorship (is )?available|will sponsor|sponsorship provided|"
            r"\bj-?1\b|\bh-?1b\b|exchange visitor|international teachers? welcome|"
            r"sponsors? (foreign|international) teachers?",
            blob,
        ):
            flags.visa_sponsorship = True
        elif re.search(r"no visa sponsorship|cannot sponsor|not able to sponsor|sponsorship not", blob):
            flags.visa_sponsorship = False
    if flags.relocation_assistance is None:
        if re.search(r"relocation (assistance|package|support)|will relocate", blob):
            flags.relocation_assistance = True
        elif re.search(r"no relocation", blob):
            flags.relocation_assistance = False

    if re.search(r"must be a (us|u\.s\.|united states|australian|eu) citizen|citizenship required", blob):
        flags.citizenship_required = True
        notes.append("explicit citizenship requirement (flagged, not auto-rejected)")
    if re.search(
        r"(must (already )?have|requires) (the right to work|unrestricted work (rights|authori[sz]ation)|"
        r"existing work (permit|visa|rights)|u\.?s\.? work authori[sz]ation)",
        blob,
    ):
        flags.work_right_required = True
        notes.append("existing work-authorisation required (flagged, not auto-rejected)")
    if re.search(r"\bj-?1\b|exchange visitor teacher", blob):
        notes.append("J-1 / exchange visitor pathway mentioned")
    if re.search(r"\bh-?1b\b", blob):
        notes.append("H-1B pathway mentioned")
    if re.search(r"self[- ]sponsor|self sponsorship|candidate.*sponsor", blob):
        notes.append("self-sponsorship language mentioned")
    if re.search(r"security clearance|nv1|nv2|sc cleared|secret clearance", blob):
        flags.security_clearance_required = True
        notes.append("security clearance required")
    if re.search(r"\b(teaching (license|licence|certificate)|state certif|certified teacher)\b", blob):
        flags.professional_registration_required = True
        notes.append("teaching licence / certification mentioned")

    flags.unknown = all(
        value is None
        for value in (
            flags.visa_sponsorship,
            flags.relocation_assistance,
            flags.work_right_required,
            flags.citizenship_required,
        )
    )
    if flags.unknown:
        notes.append("visa/work-authorisation status unknown — not inferred")
    flags.work_authorisation_notes = "; ".join(notes) if notes else None
    return flags
