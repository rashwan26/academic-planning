from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, abort, g
import sys, os
import secrets
import hmac
import re
import csv
import io
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))

from file_manager import FileManager
from planner import Planner, get_load_status, total_hours_done, calculate_gpa
from data.courses_data import COURSES_DATA

app = Flask(__name__)
instance = Path(app.instance_path)
instance.mkdir(parents=True, exist_ok=True)
key_path = instance / ".session-key"
if not os.environ.get("SECRET_KEY") and not key_path.exists():
    try:
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as key_file:
            key_file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
app.secret_key = os.environ.get("SECRET_KEY") or key_path.read_text().strip()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
                  MAX_CONTENT_LENGTH=64 * 1024)
fm = FileManager()

COURSE_MAP = {c["code"]: c for c in COURSES_DATA}
VALID_GRADES = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "F"}

@app.context_processor
def template_security():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["csrf_token"]}

@app.before_request
def protect_and_validate():
    if session.get("student_id") and not fm.load_student(session["student_id"]):
        session.clear()
    if request.method != "POST":
        return
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not supplied.isascii() or len(supplied) > 128 or not hmac.compare_digest(supplied, expected):
        return jsonify(ok=False, message="Your form expired. Reload the page and try again."), 400
    if request.endpoint not in {"login", "register"} and not session.get("student_id"):
        return jsonify(ok=False, message="Please sign in."), 401
    if request.endpoint in {"login", "register"}:
        sid = request.form.get("student_id", "").strip()
        fm._path(sid)
        password = request.form.get("password", "")
        if len(password) > 128 or not password:
            raise ValueError("Enter a password of at most 128 characters.")
    if request.endpoint == "register":
        if not 1 <= len(request.form.get("name", "").strip()) <= 100:
            raise ValueError("Name must contain 1-100 characters.")
        if len(password) < 8 or password != request.form.get("confirm_password", ""):
            raise ValueError("Use at least 8 characters and matching passwords.")
        for course in COURSES_DATA:
            grade = request.form.get("grade_" + course["code"], "").strip().upper()
            if grade and grade not in VALID_GRADES:
                raise ValueError("Invalid course grade.")
    if request.is_json:
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        field = {"update_grades": "updates", "add_new_courses": "entries"}.get(request.endpoint)
        if field:
            entries = data.get(field)
            if not isinstance(entries, list) or not 1 <= len(entries) <= len(COURSE_MAP):
                raise ValueError("Provide a non-empty course list.")
            seen = set()
            for item in entries:
                if not isinstance(item, dict):
                    raise ValueError("Invalid course entry.")
                code, grade = item.get("code"), item.get("grade")
                if not isinstance(code, str) or code not in COURSE_MAP or code in seen:
                    raise ValueError("Unknown or duplicate course code.")
                if not isinstance(grade, str) or grade not in VALID_GRADES:
                    raise ValueError("Invalid course grade.")
                seen.add(code)
                item["name"] = COURSE_MAP[code]["name"]
            if request.endpoint == "update_grades":
                student = fm.load_student(session["student_id"])
                known = {c["code"] for c in student["passed_courses"] + student["failed_courses"]}
                if not seen <= known:
                    raise ValueError("Only recorded courses can be updated.")
    elif request.endpoint in {"add_new_courses", "update_grades", "plan_with_overload"}:
        raise ValueError("Expected an application/json request.")
    fm.lock.acquire()
    g.records_locked = True

@app.teardown_request
def release_records_lock(error=None):
    if getattr(g, "records_locked", False):
        fm.lock.release()

@app.errorhandler(ValueError)
def invalid_input(error):
    if request.is_json or request.endpoint in {"add_new_courses", "update_grades", "plan_with_overload"}:
        return jsonify(ok=False, message=str(error)), 400
    flash(str(error), "danger")
    return redirect(url_for("register" if request.endpoint == "register" else "login"))

@app.errorhandler(400)
def malformed_request(error):
    return jsonify(ok=False, message="Malformed request. Reload the page and try again."), 400

@app.after_request
def response_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response

# ─── Auth ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        sid = request.form.get("student_id", "").strip()
        password = request.form.get("password", "")
        student = fm.authenticate(sid, password)
        if student is None:
            flash("Invalid registration number or password.", "danger")
            return render_template("login.html"), 401
        session.clear()
        session["student_id"] = sid
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─── Register ────────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        sid  = request.form.get("student_id", "").strip()
        if not name or not sid:
            flash("Name and Student ID are required.", "danger")
            return render_template("register.html", courses=COURSES_DATA)
        if fm.student_exists(sid):
            flash("A student with this ID already exists.", "danger")
            return render_template("register.html", courses=COURSES_DATA)

        passed, failed = [], []
        for c in COURSES_DATA:
            grade = request.form.get(f"grade_{c['code']}", "").strip().upper()
            if grade == "":
                continue
            if grade == "F":
                failed.append({"code": c["code"], "name": c["name"], "grade": "F"})
            elif grade in {"A+","A","A-","B+","B","B-","C+","C","C-","D+","D"}:
                passed.append({"code": c["code"], "name": c["name"], "grade": grade})
            else:
                flash(f"Invalid grade '{grade}' for {c['name']}. Skipped.", "warning")

        gpa     = calculate_gpa(passed + failed)
        try:
            total_semesters   = int(request.form.get("total_semesters", 8))
            current_semester  = int(request.form.get("current_semester", 0))
            if not 2 <= total_semesters <= 16 or not 0 <= current_semester <= 32:
                raise ValueError
        except ValueError:
            flash("Check your semester numbers.", "danger")
            return render_template("register.html", courses=COURSES_DATA), 400
        student = fm.create_student(name, sid, gpa, passed, failed,
                                    total_semesters, current_semester, password=request.form.get("password", ""))

        planner = Planner(student)
        plan    = planner.generate_plan()
        fm.update_plan(sid, _plan_to_serializable(plan))

        flash(f"Account created for {name}! Calculated GPA: {gpa:.2f}", "success")
        session.clear()
        session["student_id"] = sid
        return redirect(url_for("dashboard"))

    return render_template("register.html", courses=COURSES_DATA)


# ─── Dashboard ───────────────────────────────────────────────────────────────

@app.route("/dashboard")
def dashboard():
    sid = session.get("student_id")
    if not sid:
        return redirect(url_for("login"))
    student = fm.load_student(sid)
    if not student:
        session.clear()
        return redirect(url_for("login"))

    planner      = Planner(student)
    load_info    = get_load_status(student["gpa"], student.get("gpa_option"))
    hours_done   = total_hours_done(student)
    course_status= planner.get_all_course_status()

    passed    = [c for c in course_status if c["status"] == "passed"]
    failed    = [c for c in course_status if c["status"] == "failed"]
    available = [c for c in course_status if c["status"] == "available"]
    locked    = [c for c in course_status if c["status"] == "locked"]

    plan = planner.generate_plan()
    has_failures = bool(student.get("failed_courses") or
                        any(c.get("grade") == "F" for c in student.get("passed_courses", [])))

    total_semesters  = student.get("total_semesters", 8)
    current_semester = student.get("current_semester", 0)
    remaining_semesters = max(0, total_semesters - current_semester)

    # Courses not yet taken (for the "Add New Courses" feature) — only available ones
    not_taken = available  # Only show courses whose prerequisites are met

    return render_template("dashboard.html",
        student      = student,
        load_info    = load_info,
        hours_done   = hours_done,
        total_hours  = sum(c["hours"] for c in COURSES_DATA),
        passed       = passed,
        failed       = failed,
        available    = available,
        locked       = locked,
        plan         = plan,
        has_failures = has_failures,
        not_taken    = not_taken,
        total_semesters     = total_semesters,
        current_semester    = current_semester,
        remaining_semesters = remaining_semesters,
        gpa_option   = student.get("gpa_option"),  # None | "overload" | "normal" | "half"
    )


# ─── Students Dashboard ──────────────────────────────────────────────────────

@app.route("/students")
def students_dashboard():
    sid = session.get("student_id")
    if not sid:
        return redirect(url_for("login"))
    students = [s for s in fm.list_students() if s["student_id"] == sid]
    return render_template("students_dashboard.html", students=students, current_sid=sid)


# ─── View another student (read-only) ────────────────────────────────────────

@app.route("/students/<sid>")
def view_student(sid):
    if not session.get("student_id"):
        return redirect(url_for("login"))
    if sid != session.get("student_id"):
        abort(403)
    student = fm.load_student(sid)
    if not student:
        flash("Student not found.", "warning")
        return redirect(url_for("students_dashboard"))

    planner      = Planner(student)
    load_info    = get_load_status(student["gpa"], student.get("gpa_option"))
    hours_done   = total_hours_done(student)
    course_status = planner.get_all_course_status()

    passed    = [c for c in course_status if c["status"] == "passed"]
    failed    = [c for c in course_status if c["status"] == "failed"]
    available = [c for c in course_status if c["status"] == "available"]
    locked    = [c for c in course_status if c["status"] == "locked"]
    plan      = planner.generate_plan()

    return render_template("view_student.html",
        student    = student,
        load_info  = load_info,
        hours_done = hours_done,
        total_hours= sum(c["hours"] for c in COURSES_DATA),
        passed     = passed,
        failed     = failed,
        available  = available,
        locked     = locked,
        plan       = plan,
    )


# ─── Overload decision (AJAX) ─────────────────────────────────────────────────

@app.route("/plan_with_overload", methods=["POST"])
def plan_with_overload():
    sid = session.get("student_id")
    if not sid:
        return jsonify({"ok": False})
    data           = request.get_json()
    allow_overload = data.get("allow_overload", False)
    if not isinstance(allow_overload, bool):
        abort(400)
    student        = fm.load_student(sid)
    planner        = Planner(student, allow_overload_next=allow_overload)
    plan           = planner.generate_plan()
    serialized     = _plan_to_serializable(plan)
    return jsonify({"ok": True, "plan": serialized})


# ─── Update GPA Option (manual load override) ────────────────────────────────

@app.route("/update_gpa_option", methods=["POST"])
def update_gpa_option():
    sid = session.get("student_id")
    if not sid:
        return redirect(url_for("login"))
    gpa_option = request.form.get("gpa_option", "").strip().lower()
    if gpa_option not in ("overload", "normal", "half", "auto"):
        flash("Invalid load option.", "danger")
        return redirect(url_for("dashboard"))
    # "auto" means remove override — store None
    fm.update_gpa_option(sid, None if gpa_option == "auto" else gpa_option)
    student = fm.load_student(sid)
    planner = Planner(student)
    plan    = planner.generate_plan()
    fm.update_plan(sid, _plan_to_serializable(plan))
    label_map = {
        "overload": "Overload (21 CH)",
        "normal":   "Normal Load (19 CH)",
        "half":     "Half Load (14 CH)",
        "auto":     "Auto (based on GPA)",
    }
    flash(f"Load updated to: {label_map[gpa_option]}. Academic plan recalculated!", "success")
    return redirect(url_for("dashboard"))


# ─── Update GPA ──────────────────────────────────────────────────────────────

@app.route("/update_gpa", methods=["POST"])
def update_gpa():
    sid = session.get("student_id")
    if not sid:
        return redirect(url_for("login"))
    try:
        gpa = float(request.form.get("gpa", ""))
        if not (0.0 <= gpa <= 4.0):
            raise ValueError
    except ValueError:
        flash("Invalid GPA value.", "danger")
        return redirect(url_for("dashboard"))
    fm.update_gpa(sid, gpa)
    student = fm.load_student(sid)
    planner = Planner(student)
    plan    = planner.generate_plan()
    fm.update_plan(sid, _plan_to_serializable(plan))
    flash("GPA updated and academic plan recalculated!", "success")
    return redirect(url_for("dashboard"))


# ─── Update grades (existing courses) ────────────────────────────────────────

@app.route("/update_grades", methods=["POST"])
def update_grades():
    sid = session.get("student_id")
    if not sid:
        return redirect(url_for("login"))
    data    = request.get_json()
    updates = data.get("updates", [])
    fm.update_grades(sid, updates)
    student = fm.load_student(sid)
    all_graded = student["passed_courses"] + student["failed_courses"]
    new_gpa    = calculate_gpa(all_graded)
    fm.update_gpa(sid, new_gpa)
    student  = fm.load_student(sid)
    planner  = Planner(student)
    plan     = planner.generate_plan()
    fm.update_plan(sid, _plan_to_serializable(plan))
    return jsonify({"ok": True,
                    "message": f"Grades updated. New GPA: {new_gpa:.2f}",
                    "new_gpa": new_gpa})


# ─── Add new courses (AJAX) ───────────────────────────────────────────────────

@app.route("/add_new_courses", methods=["POST"])
def add_new_courses():
    """
    Receives a list of newly taken courses with grades, merges them into the
    student's record, recalculates GPA, and regenerates the academic plan.
    """
    sid = session.get("student_id")
    if not sid:
        return jsonify({"ok": False, "message": "Not logged in."})
    data    = request.get_json()
    entries = data.get("entries", [])  # [{"code": "...", "name": "...", "grade": "..."}, ...]
    if not entries:
        return jsonify({"ok": False, "message": "No courses provided."})

    fm.add_new_courses(sid, entries)
    student    = fm.load_student(sid)
    all_graded = student["passed_courses"] + student["failed_courses"]
    new_gpa    = calculate_gpa(all_graded)
    fm.update_gpa(sid, new_gpa)
    student    = fm.load_student(sid)
    planner    = Planner(student)
    plan       = planner.generate_plan()
    fm.update_plan(sid, _plan_to_serializable(plan))
    return jsonify({"ok": True,
                    "message": f"{len(entries)} course(s) added. New GPA: {new_gpa:.2f}",
                    "new_gpa": new_gpa,
                    "plan": _plan_to_serializable(plan)})


# ─── Helpers ─────────────────────────────────────────────────────────────────

@app.route("/update_timeline", methods=["POST"])
def update_timeline():
    student = fm.load_student(session["student_id"])
    current = int(request.form.get("current_semester", ""))
    total = int(request.form.get("total_semesters", ""))
    if not 0 <= current <= 32 or not 2 <= total <= 16:
        raise ValueError("Check your semester numbers.")
    student.update(current_semester=current, total_semesters=total)
    student["academic_plan"] = _plan_to_serializable(Planner(student).generate_plan())
    fm.save_student(student)
    flash("Timeline updated. Your projection starts after the last completed semester.", "success")
    return redirect(url_for("dashboard"))

@app.route("/export_plan.csv")
def export_plan():
    sid = session.get("student_id")
    if not sid:
        return redirect(url_for("login"))
    student = fm.load_student(sid)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Semester", "Course code", "Course name", "Credit hours"])
    for semester in Planner(student).generate_plan():
        for course in semester["courses"]:
            writer.writerow([semester["label"], course["code"], course["name"], course["hours"]])
    return app.response_class(output.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=academic-plan.csv"})

def _plan_to_serializable(plan: list) -> list:
    result = []
    for sem in plan:
        result.append({
            "label":       sem["label"],
            "is_summer":   sem["is_summer"],
            "courses":     [{"code": c["code"], "name": c["name"], "hours": c["hours"]}
                            for c in sem["courses"]],
            "total_hours": sem["total_hours"],
        })
    return result


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))
