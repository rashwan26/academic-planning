import random
import pytest
from data.courses_data import COURSES_DATA
from planner import Planner, calculate_gpa, get_load_status, total_hours_done

CATALOGUE = {c['code']: c for c in COURSES_DATA}

def student(passed=(), failed=(), gpa=3.0, current=0, option=None):
    return dict(passed_courses=[dict(code=c, grade='B') for c in passed],
                failed_courses=[dict(code=c, grade='F') for c in failed],
                gpa=gpa, current_semester=current, gpa_option=option)

def assert_valid_plan(record, overload=False):
    planner = Planner(record, allow_overload_next=overload)
    plan = planner.generate_plan()
    completed = set(planner.passed)
    scheduled = set()
    for index, term in enumerate(plan):
        codes = {c['code'] for c in term['courses']}
        assert len(codes) == len(term['courses'])
        assert not codes & (completed | scheduled)
        credits = sum(c['hours'] for c in term['courses'])
        assert term['total_hours'] == credits
        limit = 9 if term['is_summer'] else (21 if overload and index == 0 else planner.load['max_hours'])
        assert credits <= limit
        if term['is_summer']:
            assert len(codes) <= 3
        for course in term['courses']:
            assert set(course['prerequisites']) <= completed
            if course['code'] in {'ECE4001', 'ECE4002'}:
                assert sum(CATALOGUE[c]['hours'] for c in completed) >= 122
                assert not term['is_summer']
        scheduled.update(codes)
        completed.update(codes)
    assert scheduled == set(CATALOGUE) - set(planner.passed)
    assert plan == Planner(record, allow_overload_next=overload).generate_plan()
    return plan

@pytest.mark.parametrize('gpa,limit', [(0,14),(1.99,14),(2,19),(3.3,19),(3.31,21),(4,21)])
def test_load_boundaries(gpa, limit):
    assert get_load_status(gpa)['max_hours'] == limit
    assert_valid_plan(student(gpa=gpa))

def test_projects_are_in_different_terms_and_never_omitted():
    plan = assert_valid_plan(student())
    positions = {c['code']: i for i,t in enumerate(plan) for c in t['courses']}
    assert positions['ECE4001'] < positions['ECE4002']

def test_only_projects_remaining():
    record = student(passed=set(CATALOGUE)-{'ECE4001','ECE4002'}, current=8)
    assert len(assert_valid_plan(record)) == 2

def test_all_completed():
    assert assert_valid_plan(student(passed=CATALOGUE)) == []

def test_starts_after_completed_semester():
    plan = assert_valid_plan(student(current=6))
    assert plan[0]['label'] == 'Sem 7'

def test_failed_course_does_not_unlock_prerequisite_or_earn_credits():
    record=student(failed=['EBA1203'])
    statuses={c['code']:c for c in Planner(record).get_all_course_status()}
    assert statuses['EBA1204']['status'] == 'locked'
    assert total_hours_done(record) == 0
    plan=assert_valid_plan(record)
    assert plan[0]['courses'][0]['code'] == 'EBA1203'

def test_credit_weighted_gpa_includes_failures_excludes_zero_credit():
    assert calculate_gpa([{'code':'EBA1203','grade':'A'}, {'code':'UNR1403','grade':'F'},
                          {'code':'ECE3000','grade':'A'}]) == 2.4

def test_manual_load_and_overload_preview():
    record=student(option='half')
    assert_valid_plan(record)
    assert_valid_plan(record, overload=True)

@pytest.mark.parametrize('seed', range(12))
def test_varied_transcripts_preserve_invariants(seed):
    rng=random.Random(seed)
    passed=[c for c in CATALOGUE if rng.random() < .35]
    failed=[c for c in CATALOGUE if c not in passed and rng.random() < .2]
    assert_valid_plan(student(passed,failed,gpa=rng.choice([1.5,2.5,3.8]),current=rng.randint(0,8)))
