import json
import os
import re
import tempfile
from filelock import FileLock
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path

STUDENTS_DIR = Path(os.environ.get("APP_DATA_DIR", Path(__file__).parent / "instance" / "students"))


class FileManager:
    def __init__(self, directory=None):
        self.directory = Path(directory or STUDENTS_DIR)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.directory / ".records.lock"), timeout=10)

    def _path(self, student_id: str) -> Path:
        if not isinstance(student_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", student_id):
            raise ValueError("Registration number must use 1-32 letters, digits, underscores or hyphens.")
        return self.directory / f"{student_id}.json"

    def student_exists(self, student_id: str) -> bool:
        return self._path(student_id).exists()

    def load_student(self, student_id: str) -> dict | None:
        p = self._path(student_id)
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_student(self, student: dict) -> None:
        sid = student["student_id"]
        p = self._path(sid)
        fd, temporary = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(student, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, p)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def create_student(self, name: str, student_id: str, gpa: float,
                       passed: list[dict], failed: list[dict],
                       total_semesters: int = 8, current_semester: int = 0, password: str = "") -> dict:
        if not 8 <= len(password) <= 128:
            raise ValueError("Password must contain 8-128 characters.")
        student = {
            "password_hash": generate_password_hash(password),
            "name": name,
            "student_id": student_id,
            "gpa": gpa,
            "passed_courses": passed,
            "failed_courses": failed,
            "academic_plan": [],
            "total_semesters": total_semesters,
            "current_semester": current_semester,
        }
        with self.lock:
            if self.student_exists(student_id):
                raise ValueError("An account already exists for that registration number.")
            self.save_student(student)
        return student

    def update_plan(self, student_id: str, plan: list) -> None:
        student = self.load_student(student_id)
        if student:
            student["academic_plan"] = plan
            self.save_student(student)

    def update_grades(self, student_id: str, updates: list[dict]) -> None:
        """Update grades for already-recorded courses."""
        student = self.load_student(student_id)
        if not student:
            return
        grade_map = {u["code"]: u["grade"] for u in updates}
        new_passed = []
        new_failed = []
        all_courses = student["passed_courses"] + student["failed_courses"]
        for c in all_courses:
            code = c["code"]
            grade = grade_map.get(code, c["grade"])
            c["grade"] = grade
            if grade == "F":
                new_failed.append(c)
            else:
                new_passed.append(c)
        student["passed_courses"] = new_passed
        student["failed_courses"] = new_failed
        self.save_student(student)

    def add_new_courses(self, student_id: str, new_entries: list[dict]) -> None:
        """
        Add newly taken courses (or update existing ones).
        new_entries = [{"code": "...", "name": "...", "grade": "..."}, ...]
        - If the course already exists in passed/failed, its grade is updated.
        - If it is new, it is inserted.
        """
        student = self.load_student(student_id)
        if not student:
            return

        # Build a unified dict keyed by code for easy lookup/update
        all_courses: dict[str, dict] = {}
        for c in student["passed_courses"] + student["failed_courses"]:
            all_courses[c["code"]] = c

        for entry in new_entries:
            code  = entry["code"]
            grade = entry["grade"].upper()
            if code in all_courses:
                all_courses[code]["grade"] = grade
            else:
                all_courses[code] = {
                    "code":  code,
                    "name":  entry.get("name", code),
                    "grade": grade,
                }

        new_passed, new_failed = [], []
        for c in all_courses.values():
            if c["grade"] == "F":
                new_failed.append(c)
            else:
                new_passed.append(c)

        student["passed_courses"] = new_passed
        student["failed_courses"] = new_failed
        self.save_student(student)

    def update_gpa(self, student_id: str, gpa: float) -> None:
        student = self.load_student(student_id)
        if student:
            student["gpa"] = gpa
            self.save_student(student)

    def update_gpa_option(self, student_id: str, gpa_option: str | None) -> None:
        """Set the student's manual load override: 'overload', 'normal', 'half', or None (auto)."""
        student = self.load_student(student_id)
        if student:
            student["gpa_option"] = gpa_option
            self.save_student(student)

    def list_students(self) -> list[dict]:
        result = []
        for p in self.directory.glob("*.json"):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                passed_list  = data.get("passed_courses", [])
                failed_list  = data.get("failed_courses", [])
                # count available: prereqs met (simple pass — planner has the full logic)
                result.append({
                    "name":       data["name"],
                    "student_id": data["student_id"],
                    "gpa":        data.get("gpa", 0.0),
                    "passed":     len([c for c in passed_list if c.get("grade","") != "F"]),
                    "failed":     len(failed_list),
                })
        return result

    def authenticate(self, student_id: str, password: str) -> dict | None:
        try:
            student = self.load_student(student_id)
        except ValueError:
            return None
        stored = student.get("password_hash", "") if student else ""
        # Legacy name-only records are never silently claimable.
        if not stored or not check_password_hash(stored, password):
            return None
        return student
