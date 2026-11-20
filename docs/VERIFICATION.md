# Verification

Verified on 20 November 2026.

- Local: 41 pytest tests passed on Python 3.10.
- GitHub Actions: 41 tests passed on each of Python 3.10 and 3.12 in [run 44822307895](https://github.com/rashwan26/academic-planning/actions/runs/44822307895).
- Browser: created a fictional student, entered passing/failing grades, generated the roadmap, changed a failing grade to B through the dashboard, and observed GPA recalculate from 2.00 to 3.50.
- Visual review: checked dashboard and roadmap; fixed unreadable light-theme tab and header colors.
- Publication check: student JSON files, session keys, caches and environment secrets are excluded from Git and the downloadable archive. Screenshots contain fictional data.

The automated suite tests all remaining-course coverage, prerequisite order, graduation-project eligibility, credit limits, summer limits, determinism, complete transcripts, varying transcripts, authentication, password storage, privacy, input validation, CSRF, grade persistence, timeline advancement and CSV export.

This does not verify official academic policy, live course availability, optimal graduation time or a production deployment. See PLANNING.md for the model's assumptions.
