import pytest
import app as web
from file_manager import FileManager

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'fm', FileManager(tmp_path/'students'))
    web.app.config.update(TESTING=True, SECRET_KEY='test-only-key')
    return web.app.test_client()

def token(client, page='/'):
    client.get(page)
    with client.session_transaction() as session:
        return session['csrf_token']

def register(client, sid='DEMO001'):
    return client.post('/register', data=dict(csrf_token=token(client,'/register'),
        name='Demo Student', student_id=sid, password='Local-demo-123',
        confirm_password='Local-demo-123', total_semesters=8,current_semester=0,
        grade_EBA1203='A',grade_EBA1103='F'))

def test_registration_hashed_password_and_dashboard(client):
    assert register(client).status_code == 302
    record=web.fm.load_student('DEMO001')
    assert record['password_hash'] != 'Local-demo-123'
    assert 'password' not in record
    result=client.get('/dashboard')
    assert result.status_code == 200
    assert b'Academic Planning' in result.data
    assert b'145' in result.data

def test_password_login_and_csrf_rotation(client):
    register(client)
    before=token(client)
    client.post('/logout',data={'csrf_token':before})
    result=client.post('/',data=dict(csrf_token=token(client),student_id='DEMO001',password='wrong'))
    assert result.status_code == 401
    result=client.post('/',data=dict(csrf_token=token(client),student_id='DEMO001',password='Local-demo-123'))
    assert result.status_code == 302
    assert token(client) != before

def test_csrf_required_for_forms_and_json(client):
    assert client.post('/register',data={}).status_code == 400
    register(client)
    assert client.post('/update_grades',json={'updates':[]}).status_code == 400

def test_transcripts_private(client):
    register(client)
    web.fm.create_student('Other Student','OTHER',3,[],[],password='Another-pass-123')
    assert client.get('/students/OTHER').status_code == 403
    assert b'Other Student' not in client.get('/students').data
    client.post('/logout',data={'csrf_token':token(client)})
    page=client.get('/').data
    assert b'Demo Student' not in page and b'OTHER' not in page

@pytest.mark.parametrize('sid',['../escape','/tmp/escape','with space','a'*33])
def test_registration_path_validation(client,sid):
    result=register(client,sid)
    assert result.status_code == 302
    assert not list(web.fm.directory.glob('*.json'))

def test_invalid_json_and_courses_do_not_change_transcript(client):
    register(client)
    original=web.fm.load_student('DEMO001')
    header={'X-CSRF-Token':token(client)}
    for data in [None, [], {'entries':[{'code':'UNKNOWN','grade':'A'}]},
                 {'entries':[{'code':'EBA1203','grade':'INVALID'}]},
                 {'entries':[{'code':'EBA1203','grade':'A'}]*2}]:
        result=client.post('/add_new_courses',json=data,headers=header)
        assert result.status_code == 400
    assert web.fm.load_student('DEMO001') == original

def test_grade_update_recalculates_gpa_and_plan(client):
    register(client)
    result=client.post('/update_grades',headers={'X-CSRF-Token':token(client)},
        json={'updates':[{'code':'EBA1103','grade':'B'}]})
    assert result.status_code == 200 and result.json['ok']
    record=web.fm.load_student('DEMO001')
    assert record['gpa'] == 3.5 and not record['failed_courses']
    assert record['academic_plan']

def test_course_name_is_canonical_and_grade_preserved(client):
    register(client)
    result=client.post('/add_new_courses',headers={'X-CSRF-Token':token(client)},
        json={'entries':[{'code':'UNR1403','grade':'A','name':'<script>bad</script>'}]})
    assert result.json['ok']
    record=web.fm.load_student('DEMO001')
    course=next(c for c in record['passed_courses'] if c['code']=='UNR1403')
    assert course['name']=='Academic English'
    status=next(c for c in web.Planner(record).get_all_course_status() if c['code']=='UNR1403')
    assert status['grade']=='A'

def test_legacy_name_only_record_cannot_be_claimed(client):
    web.fm.save_student(dict(name='Legacy',student_id='LEGACY',gpa=0,passed_courses=[],failed_courses=[]))
    assert web.fm.authenticate('LEGACY','Legacy') is None

def test_manual_load_badge_agrees_with_plan(client):
    register(client)
    result=client.post('/update_gpa_option',data={'csrf_token':token(client),'gpa_option':'normal'},follow_redirects=True)
    assert b'Normal Load (Manual Override' in result.data
    record=web.fm.load_student('DEMO001')
    assert all(t['total_hours'] <= (9 if t['is_summer'] else 19) for t in record['academic_plan'])

def test_csv_export_requires_login_and_contains_projected_courses(client):
    assert client.get('/export_plan.csv').status_code==302
    register(client)
    result=client.get('/export_plan.csv')
    assert result.status_code==200
    assert result.mimetype=='text/csv'
    assert b'Course code' in result.data and b'ECE4002' in result.data

def test_advancing_timeline_moves_projection_start(client):
    register(client)
    result=client.post('/update_timeline',data={'csrf_token':token(client),
        'current_semester':4,'total_semesters':8})
    assert result.status_code==302
    record=web.fm.load_student('DEMO001')
    assert record['current_semester']==4
    assert record['academic_plan'][0]['label']=='Sem 5'

def test_non_ascii_csrf_is_rejected_without_server_error(client):
    register(client)
    assert client.post('/logout', data={'csrf_token':'é'}).status_code==400
