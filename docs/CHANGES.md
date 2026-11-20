# Changes from the supplied application

- Renamed the app and repository to Academic Planning.
- Replaced name/registration-number login with registration number and a hashed password.
- Removed the public account/grade directory and restricted transcript views to their owner.
- Added CSRF protection to forms and JSON updates; logout now requires POST.
- Replaced the hardcoded session secret with private local generation or an environment setting.
- Validated registration numbers before forming a file path; bounded names, passwords, semester inputs and payload size.
- Reject invalid/duplicate course entries and use canonical catalogue names rather than client-provided names.
- Fixed storage location to an ignored per-project instance directory; added locking and atomic file replacement.
- Replaced the graduation-project injection algorithm with a single deterministic scheduling path. Project II follows Project I in a later term, projects count against the term limit, and incomplete plans raise an error.
- Started projections after the student's completed semester and retained the supplied earliest-semester placement rules.
- Restored recorded grades in course-status objects and kept the displayed load badge consistent with saved overrides.
- Calculated the catalogue total instead of hardcoding 144; the supplied data totals 145 credits.
- Added CSV export, documented assumptions, pinned dependencies and regression tests.

No university-portal integration, official curriculum verification, production hosting or optimization guarantee was added. There were no real student records in the supplied archive; none are published by this project.
