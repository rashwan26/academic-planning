# Planning assumptions and boundaries

The plan is built from the entered transcript. A recorded passing grade adds the course to the completed set; F does not earn credits or satisfy a prerequisite. After each projected term, its selected courses are assumed to pass and can unlock later terms. The actual transcript is unchanged by planning.

Planning starts after the last completed regular semester, with 0 meaning no completed semester. Catalogue semester values are earliest eligible placements. Every second regular term can be followed by a summer projection. In summer, an eligible course must be failed or overdue relative to its catalogue semester, and training/projects are excluded. Summer attendance is a model assumption, not a verified offering calendar.

At each term start, the planner checks dependencies, eligibility and available credits. It chooses eligible failed courses first, then catalogue semester, then course code. Selection is deterministic. Because dependencies are evaluated before selection, a prerequisite and dependent cannot be added together. Graduation projects use this same mechanism: they are never appended after capacity checks. Project eligibility uses credits completed before the term starts, not credits gained later in that term.

The search horizon is bounded at 80 regular terms. If courses remain, the planner raises an explicit failure rather than returning a partial plan and claiming graduation. For the bundled acyclic catalogue, tests verify every remaining course appears exactly once. A feasible plan is not necessarily the shortest possible plan.

GPA uses the latest recorded grade for each course in this application, weighted by its listed credits. F contributes zero points but counts as attempted credits. Zero-credit practical training is excluded from GPA. Prior attempts are not retained as an attempt history; institutional repeat-course GPA policies are not modeled. An explicit GPA override can differ from the grades until a later grade update recalculates it.

The manual load choices and overload preview are scenarios. The app cannot approve an overload or check an official registration policy. CSV exports use the saved grade/load settings, not an unsaved one-term preview.

The catalogue sums to 145 credits, while the original README stated 144. The catalogue was preserved unchanged and the application displays its calculated sum. Confirm course credits, prerequisites, training requirements, project eligibility, official GPA scale and semester availability against the actual curriculum before relying on the result.
