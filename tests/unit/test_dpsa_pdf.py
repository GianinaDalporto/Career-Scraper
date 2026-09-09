from pathlib import Path

from job_scout.services.dpsa_pdf import is_engineering_relevant, parse_circular_text, pdf_bytes_to_text


SAMPLE = """
POST 32/252 : CHIEF ENGINEER, GRADE A REF NO: LDOE 07/09/2026
  Directorate: Physical Resources Management (Infrastructure)

SALARY : R1 317 384 per annum
CENTRE  Head Office, Polokwane
REQUIREMENTS : An engineering qualification (B Engineering / BSc in Engineering) at NQF level
07 as recognised by SAQA. Valid Registration with professional Engineer - ECSA.
DUTIES : Perform final review and approvals or audits on new engineering designs
CLOSING DATE : 18 September 2026

POST 32/999 : CLEANER REF NO: X1
SALARY : R130 000 per annum
CENTRE : Pretoria
REQUIREMENTS : Grade 10
DUTIES : Clean offices
CLOSING DATE : 18 September 2026

POST 32/262 : CIVIL/ STRUCTURAL ENGINEER (GRADE A-C) REF NO: S.4/3/13/6
  Component: Health and Education Infrastructure Delivery

SALARY : Grade A: R914 517 per annum
  Grade B: R1 030 296 per annum
  Grade C: R1 172 184 per annum
CENTRE : Head Office – Polokwane
REQUIREMENTS : Compulsory valid registration with ECSA as Professional Engineer.
DUTIES : Design and supervise civil works
CLOSING DATE : 25 September 2026
"""


def test_parse_dpsa_keeps_engineers_drops_cleaner():
    posts = parse_circular_text(
        SAMPLE,
        source_pdf_url="https://www.dpsa.gov.za/dpsa2g/documents/vacancies/2026/32/s.pdf",
        department_hint="Limpopo",
    )
    ids = {p.post_id for p in posts}
    assert "32/252" in ids
    assert "32/262" in ids
    assert "32/999" not in ids
    chief = next(p for p in posts if p.post_id == "32/252")
    assert "CHIEF ENGINEER" in chief.title.upper()
    assert chief.salary_text and "1 317 384" in chief.salary_text
    assert chief.centre and "Polokwane" in chief.centre


def test_engineering_relevance():
    assert is_engineering_relevant("CHIEF ENGINEER, GRADE A", "")
    assert not is_engineering_relevant("CLEANER", "general office cleaning")


def test_pdf_bytes_roundtrip_sample_file():
    path = Path(".tmp_dpsa/s32.pdf")
    if not path.exists():
        return
    text = pdf_bytes_to_text(path.read_bytes())
    posts = parse_circular_text(
        text,
        source_pdf_url="https://example.com/s.pdf",
        department_hint="Limpopo",
    )
    assert any("CHIEF ENGINEER" in p.title.upper() for p in posts)
