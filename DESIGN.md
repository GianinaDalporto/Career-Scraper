# Nina Career Scraper — Design Brief

Working title: **Nina Scout** (teacher / education jobs, USA-first).

This project will reuse the architecture of [Career-Python-Scraper (Job Scout)](https://github.com/tiaandelange/Career-Python-Scraper). A durable handoff of that system is being written to:

`C:\Users\Tiaan\GitHub\Career-Python-Scraper\docs\FORK_HANDOFF.md`

---

## Goal

Find and email Nina roles that fit:

1. **Primary:** Teaching (and closely related classroom) positions **in the United States** (onsite / hybrid), especially where **visa sponsorship (J-1 / H-1B)** or **self-sponsorship pathways** are realistic.
2. **Secondary:** **Remote** education work (online teaching, tutoring, curriculum, edtech) and **admin / school-office** support roles that a teacher’s skills transfer into.
3. Prefer employers who **sponsor**, **work with J-1 sponsors**, or are open to candidates who can **self-sponsor / already hold** a visa — without inventing immigration advice.

---

## Role families (proposed — confirm / edit)

### A. Classroom teaching (onsite USA — highest priority)

| Family | Example titles |
|--------|----------------|
| Elementary / primary | Elementary Teacher, Grade Teacher, Homeroom |
| Secondary subject | Math, Science, English/ELA, Social Studies, History |
| Special education | Special Education Teacher, SPED, Inclusion |
| ESL / bilingual | ESL Teacher, ELD, ELL, Bilingual Teacher |
| Early childhood | Preschool, Kindergarten, Pre-K |
| Specialist | Music, Art, PE, Library/Media (if Nina wants these) |

**Visa note:** Many districts recruit internationals via **J-1 Exchange Visitor (Teacher)** programs (e.g. large urban districts). **H-1B** is less common for K-12 and more policy-sensitive; still flag when ads mention sponsorship.

### B. Remote / flexible education (second priority)

| Family | Example titles | Notes |
|--------|----------------|-------|
| Online ESL / English tutoring | Online ESL Teacher, Language Tutor | Often contractor; may require US work auth already |
| Virtual K-12 teacher | Online Teacher, Virtual Academy Teacher | Usually needs state license + US presence |
| Curriculum / instructional design | Curriculum Specialist, Instructional Designer (education) | Strong transfer from teaching |
| Edtech content / training | Content Writer (education), Learning Experience, Teacher Success |
| Academic support | Tutor (K-12), Interventionist (remote) | |

### C. Admin / operations adjacent (third priority)

| Family | Example titles |
|--------|----------------|
| School admin support | Administrative Assistant (school/district), Registrar Aide, Office Manager (school) |
| Academic admin | Admissions Assistant, Student Services Coordinator |
| Program coordination | Program Coordinator (education/nonprofit), Scheduling Coordinator |

**Out of scope unless you say otherwise:** pure corporate admin with no education link; university tenure-track research faculty; daycare-only with no teaching credential path.

---

## Geographic & mobility policy (proposed)

| Mode | Rule |
|------|------|
| Onsite / hybrid | Country must resolve to **US** (City, ST parsing). Prefer states Nina is willing to live in (TBD). |
| Remote | Prefer **US-based remote** or worldwide remote that does **not** exclude non-US citizens. Soft-flag “must already have US work authorization” vs hard-reject (TBD). |
| Sponsorship | Boost / flag: `visa sponsorship`, `J-1`, `H-1B`, `will sponsor`, `international teachers`, `visa support`. Self-sponsorship interest → do **not** reject merely because sponsorship is “unknown”. |

---

## What we will copy from Job Scout

- Adapter → normalise → hard filters → score → Supabase → Resend digest
- ATS adapters (Greenhouse, Lever, Ashby, SmartRecruiters, Workable) with **education employers**
- USAJOBS (optional) for federal education-adjacent roles
- Schema-aware Supabase client, GitHub Actions scrape/digest/health
- Dedup, apply-url persistence, reject handling

## What we will drop or replace

- Dam / mechanical / DPSA / ZA-centric profile and salary floors
- SA government PDF circular adapter (unless Nina wants something similar later)
- Engineering job families and keywords

## Likely new sources (to confirm)

- District career pages / AppliTrack / Frontline (many US districts)
- Teachers-Teachers, SchoolSpring (if scrapable / ToS-safe)
- J-1 sponsor / international teacher program listings (manual seed list first)
- Edtech ATS boards (Amplify, Curriculum Associates, etc.)
- RemoteOK / Jobicy / similar **only** for education keywords (noisy — gated tightly)

---

## Open questions for you (please answer)

Reply with short answers; defaults in *(italics)* if you skip.

1. **Nina’s subject(s) / grades?** e.g. elementary, high-school math, ESL, SPED… *(unknown → keep broad K-12 + ESL)*
2. **Credentials?** teaching license, PGCE, TEFL/TESOL, years of experience, languages *(unknown)*
3. **Nationality / current country?** affects J-1 eligibility messaging in digests *(South Africa?)*
4. **Willing to relocate to which US states / regions?** or any US? *(any US)*
5. **Remote priority:** full-time remote only, or part-time tutoring OK? *(include part-time remote)*
6. **Admin assistant:** school/education admin only, or any US admin assistant role? *(education-linked only)*
7. **Salary floor (USD monthly or annual)?** teaching salaries vary widely by district *(soft floor or none at first)*
8. **Hard-reject if ad says “must have US work authorization already”?** *(flag, don’t hard-reject — you said self-sponsorship OK)*
9. **Digest email address** and same Resend/Supabase setup as Job Scout, or separate project/secrets? *(separate Supabase project recommended)*
10. **Repo name / GitHub visibility:** `Nina-Career-Scraper` private? *(private)*

---

## Next steps (after your answers)

1. Finish storing Job Scout handoff (`docs/FORK_HANDOFF.md`).
2. Copy Job Scout codebase into this folder and rename package (`nina_scout` or keep `job_scout`).
3. Rewrite `config/profile.yaml`, `scoring.yaml`, `salary_policy.yaml`, `sources.yaml`.
4. Adjust eligibility for USA + sponsorship flags.
5. Wire GitHub Actions + Supabase + digest.
6. Run a dry scrape and tune false positives.
