# Nina Career Scraper — Design Brief

Working title: **Nina Scout** (teacher / education / US admin jobs).

Fork of Job Scout. Handoff: `docs/FORK_HANDOFF.md`.

---

## Confirmed profile (2026-09-09)

| Item | Answer |
|------|--------|
| Focus | Primary teacher, **grades 1–5** |
| Credentials | B.Ed, **TEFL**, ~**4 years**, fluent **Afrikaans + English** |
| Nationality | **South African** |
| US relocate | Southern / Bible Belt–style: **TX, AL, TN, SC, NC, KY, FL, CO, GA** (+ similar) |
| Remote | **Full-time and part-time** tutoring OK |
| Admin | **Any US admin** assistant role |
| Salary floor | **USD 2 800 / mo** or **ZAR 40 000 / mo** |
| “Must have US work auth” | **Flag only** (no hard reject) |
| Infrastructure | Separate Supabase + Resend from Job Scout |
| GitHub | Public **`GianinaDalporto/Career-Scraper`** |

---

## Role families (configured)

1. **Primary teaching** — elementary / grades 1–5 / classroom  
2. **ESL / language** — ESL, ELL, TEFL, online English, bilingual  
3. **Remote education** — online/virtual teacher, tutor, curriculum, edtech  
4. **Admin assistant** — any US admin/office assistant titles  

---

## Policy notes

- Onsite/hybrid target country: **US only**
- Preferred states get a score boost; other US states still allowed  
- US-only remote is **accepted** (not rejected as for the ZA engineer profile)  
- Onsite salary often unpublished on district ads → **flag**, do not reject  
- Sponsorship phrases (J-1, H-1B, will sponsor, international teachers) **boost** score  
- Citizenship / existing work-auth language → **concerns + mild penalty**, not hard reject  

---

## Next for you

1. Create Supabase project → run `supabase/migrations/0001_init.sql`  
2. Create Resend key + verified sender  
3. Create GitHub repo `GianinaDalporto/Career-Scraper` (public) and add Actions secrets  
4. Add more US district / edtech ATS employer slugs to `config/sources.yaml` as you find them  
