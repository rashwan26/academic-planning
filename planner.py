from data.courses_data import COURSES_DATA

GRADE_PASS = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D"}

OVERLOAD_HOURS   = 21
NORMAL_HOURS     = 19
HALF_HOURS       = 14
SUMMER_MAX_HOURS = 9

PRACTICAL_1_CODE = "ECE3000"
PRACTICAL_2_CODE = "ECE4000"

GRAD_PROJECT_CODES     = {"ECE4001", "ECE4002"}
GRAD_PROJECT_MIN_HOURS = 122
GRAD_PROJECT_1_CODE    = "ECE4001"
GRAD_PROJECT_2_CODE    = "ECE4002"

GRADE_POINTS = {
    "A+": 4.0, "A": 4.0, "A-": 3.7,
    "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7,
    "D+": 1.3, "D": 1.0, "F": 0.0,
}

_IDX_TO_SEM_NUM = {0: 1, 1: 2, 3: 3, 4: 4, 6: 5, 7: 6, 9: 7, 10: 8}


def calculate_gpa(courses: list) -> float:
    course_map = {c["code"]: c for c in COURSES_DATA}
    total_points, total_hours = 0.0, 0
    for c in courses:
        grade, code = c.get("grade", ""), c.get("code", "")
        if grade not in GRADE_POINTS:
            continue
        info = course_map.get(code)
        if not info or info["hours"] == 0:
            continue
        h = info["hours"]
        total_points += GRADE_POINTS[grade] * h
        total_hours  += h
    return round(total_points / total_hours, 2) if total_hours else 0.0


def semester_label(idx: int) -> str:
    order = [
        "Sem 1", "Sem 2", "Summer 1",
        "Sem 3", "Sem 4", "Summer 2",
        "Sem 5", "Sem 6", "Summer 3",
        "Sem 7", "Sem 8", "Summer 4",
    ]
    return order[idx] if idx < len(order) else f"Extra {idx - 11}"


def is_summer(idx: int) -> bool:
    return idx in {2, 5, 8, 11}


def get_load_status(gpa: float, gpa_option: str = None) -> dict:
    """
    Returns the load status based on GPA.
    If gpa_option is provided ('overload', 'normal', 'half'), it overrides the
    automatic GPA-based calculation — the student manually chose their load.
    """
    if gpa_option == "overload":
        return {"status": "Overload",  "max_hours": OVERLOAD_HOURS,
                "label": "Overload (Manual Override — 21 CH)", "color": "success",
                "manual": True}
    elif gpa_option == "normal":
        return {"status": "Normal",    "max_hours": NORMAL_HOURS,
                "label": "Normal Load (Manual Override — 19 CH)", "color": "primary",
                "manual": True}
    elif gpa_option == "half":
        return {"status": "Half",      "max_hours": HALF_HOURS,
                "label": "Half Load (Manual Override — 14 CH)", "color": "danger",
                "manual": True}
    # Auto based on GPA
    if gpa > 3.3:
        return {"status": "Overload",  "max_hours": OVERLOAD_HOURS,
                "label": "Overload (GPA > 3.3)",          "color": "success",
                "manual": False}
    elif gpa >= 2.0:
        return {"status": "Normal",    "max_hours": NORMAL_HOURS,
                "label": "Normal Load (2.0 \u2264 GPA \u2264 3.3)", "color": "primary",
                "manual": False}
    else:
        return {"status": "Half",      "max_hours": HALF_HOURS,
                "label": "Half Load (GPA < 2.0)",          "color": "danger",
                "manual": False}


def total_hours_done(student: dict) -> int:
    passed_codes = {c["code"] for c in student["passed_courses"] if c.get("grade") in GRADE_PASS}
    return sum(c["hours"] for c in COURSES_DATA if c["code"] in passed_codes)


def calculate_hours_per_semester(student: dict) -> dict:
    passed_codes = {c["code"] for c in student["passed_courses"] if c.get("grade") in GRADE_PASS}
    sem_hours = {}
    for c in COURSES_DATA:
        if c["code"] in passed_codes and c["semester"]:
            s = c["semester"]
            sem_hours[s] = sem_hours.get(s, 0) + c["hours"]
    return sem_hours


class Planner:
    def __init__(self, student: dict, allow_overload_next: bool = False):
        self.student = student
        self.courses = {c["code"]: c for c in COURSES_DATA}
        all_passed       = {c["code"] for c in student["passed_courses"]}
        actually_failed  = {c["code"] for c in student["passed_courses"]
                            if c["grade"] == "F"}
        self.passed      = all_passed - actually_failed
        self.failed      = ({c["code"] for c in student.get("failed_courses", [])}
                            | actually_failed)
        self.gpa         = student["gpa"]
        gpa_option       = student.get("gpa_option")  # None | "overload" | "normal" | "half"
        self.load        = get_load_status(self.gpa, gpa_option)
        self.allow_overload_next = allow_overload_next

    def _prereqs_met(self, code: str, available: set) -> bool:
        c = self.courses.get(code)
        return c is not None and all(p in available for p in c["prerequisites"])

    def _missing_prereqs(self, code: str, available: set) -> list:
        c = self.courses.get(code)
        return [p for p in c["prerequisites"] if p not in available] if c else []

    def _has_prereq_conflict(self, code_a: str, code_b: str) -> bool:
        """Return True if code_a is a prereq of code_b, or code_b is a prereq of code_a."""
        ca = self.courses.get(code_a)
        cb = self.courses.get(code_b)
        if ca and cb:
            if code_a in cb.get("prerequisites", []):
                return True
            if code_b in ca.get("prerequisites", []):
                return True
        return False

    def get_all_course_status(self) -> list:
        result     = []
        hours_done = total_hours_done(self.student)
        for c in COURSES_DATA:
            code = c["code"]
            base = {**c, "grade": next((x["grade"] for x in self.student["passed_courses"] + self.student.get("failed_courses", []) if x["code"] == code), ""), "missing_prereqs": [], "missing_names": [], "locked_reason": None}
            if code in self.passed:
                result.append({**base, "status": "passed"})
            elif code in self.failed:
                result.append({**base, "status": "failed"})
            elif self._prereqs_met(code, self.passed):
                if (c.get("semester") or 1) > self.student.get("current_semester", 0) + 1:
                    result.append({**base, "status": "locked",
                                   "locked_reason": f"Earliest placement: regular semester {c['semester']}"})
                elif code in GRAD_PROJECT_CODES and hours_done < GRAD_PROJECT_MIN_HOURS:
                    result.append({**base, "status": "locked",
                                   "locked_reason": f"Requires {GRAD_PROJECT_MIN_HOURS} credit hours completed ({hours_done} done)"})
                else:
                    result.append({**base, "status": "available"})
            else:
                missing = self._missing_prereqs(code, self.passed)
                result.append({**base, "status": "locked",
                                "missing_prereqs": missing,
                                "missing_names": [self.courses[m]["name"]
                                                  for m in missing if m in self.courses]})
        return result

    def generate_plan(self) -> list:
        """Greedy projection: all dependencies must have passed in an earlier term.

        Current semester means the last completed regular semester (0 for new
        students). Summer supports up to three retakes / overdue courses and
        nine credits. All projected courses are assumed to pass.
        """
        completed = set(self.passed)
        remaining = set(self.courses) - completed
        current = int(self.student.get("current_semester", 0))
        regular = current + 1
        plan = []
        for _ in range(80):
            for summer in (False, True):
                if summer and regular % 2:
                    continue
                hours_done = sum(self.courses[code]["hours"] for code in completed)
                candidates = []
                for code in remaining:
                    course = self.courses[code]
                    if not self._prereqs_met(code, completed):
                        continue
                    if code in GRAD_PROJECT_CODES:
                        if summer or hours_done < GRAD_PROJECT_MIN_HOURS:
                            continue
                    if code in {PRACTICAL_1_CODE, PRACTICAL_2_CODE} and summer:
                        continue
                    canonical = course.get("semester") or 1
                    if canonical > regular:
                        continue
                    if summer and not (code in self.failed or canonical < regular):
                        continue
                    candidates.append(course)
                candidates.sort(key=lambda c: (c["code"] not in self.failed,
                                                c.get("semester") or 1, c["code"]))
                limit = SUMMER_MAX_HOURS if summer else self.load["max_hours"]
                if not plan and not summer and self.allow_overload_next:
                    limit = OVERLOAD_HOURS
                chosen, hours = [], 0
                for course in candidates:
                    if summer and len(chosen) >= 3:
                        break
                    if hours + course["hours"] <= limit:
                        chosen.append(course)
                        hours += course["hours"]
                if chosen:
                    plan.append({"label": f"Summer {regular // 2}" if summer else f"Sem {regular}",
                                 "is_summer": summer, "semester_idx": len(plan),
                                 "courses": chosen, "total_hours": hours})
                    codes = {c["code"] for c in chosen}
                    completed.update(codes)
                    remaining.difference_update(codes)
                if not remaining:
                    return plan
            regular += 1
        raise ValueError("A complete plan could not be generated. Check catalogue dependencies and credit limits.")
