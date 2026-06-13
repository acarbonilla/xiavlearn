import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


API_BASE_URL = os.environ.get(
    'API_BASE_URL',
    'http://127.0.0.1:8000',
).rstrip('/')
TEST_USERNAME = os.environ.get('TEST_USERNAME')
TEST_PASSWORD = os.environ.get('TEST_PASSWORD')


class SmokeTestError(RuntimeError):
    pass


def request_json(path, method='GET', payload=None, authenticated=False):
    headers = {'Accept': 'application/json'}
    if authenticated:
        credentials = f'{TEST_USERNAME}:{TEST_PASSWORD}'.encode('utf-8')
        token = base64.b64encode(credentials).decode('ascii')
        headers['Authorization'] = f'Basic {token}'

    body = None
    if payload is not None:
        body = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    request = urllib.request.Request(
        f'{API_BASE_URL}{path}',
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            content = response.read().decode('utf-8')
            return response.status, json.loads(content)
    except urllib.error.HTTPError as exc:
        content = exc.read().decode('utf-8')
        try:
            error_data = json.loads(content)
        except json.JSONDecodeError:
            error_data = content
        raise SmokeTestError(
            f'{method} {path} returned {exc.code}: {error_data}'
        ) from exc
    except urllib.error.URLError as exc:
        raise SmokeTestError(
            f'Could not reach {API_BASE_URL}: {exc.reason}'
        ) from exc


def require(condition, message):
    if not condition:
        raise SmokeTestError(message)


def agent_data(path, method='GET', payload=None):
    status_code, response = request_json(
        path,
        method=method,
        payload=payload,
        authenticated=True,
    )
    require(response.get('success') is True, f'{path} did not report success.')
    require('data' in response, f'{path} response is missing data.')
    require(response.get('message'), f'{path} response is missing message.')
    print(f'PASS {method} {path} ({status_code})')
    return response['data']


def main():
    if not TEST_USERNAME or not TEST_PASSWORD:
        raise SmokeTestError(
            'Set TEST_USERNAME and TEST_PASSWORD before running the smoke test.'
        )

    public_paths = [
        '/api/health/',
        '/api/skills/',
        '/api/levels/',
        '/api/modules/',
        '/api/modules/?level_code=A2',
        '/api/modules/?skill=Grammar',
    ]
    for path in public_paths:
        status_code, _ = request_json(path)
        print(f'PASS GET {path} ({status_code})')

    _, modules = request_json('/api/modules/')
    require(modules, 'No active modules were returned.')
    module_id = modules[0]['id']
    status_code, _ = request_json(f'/api/modules/{module_id}/')
    print(f'PASS GET /api/modules/{module_id}/ ({status_code})')

    _, current_user = request_json('/api/auth/me/', authenticated=True)
    require(
        current_user.get('username') == TEST_USERNAME,
        'Authenticated user does not match TEST_USERNAME.',
    )
    print('PASS GET /api/auth/me/ (200)')

    _, profile = request_json('/api/profile/', authenticated=True)
    profile_patch = {
        'target_level': profile.get('target_level') or 'B2',
        'daily_study_minutes': profile.get('daily_study_minutes') or 30,
        'learning_goal': 'Sprint 3 API smoke test',
    }
    status_code, profile = request_json(
        '/api/profile/',
        method='PATCH',
        payload=profile_patch,
        authenticated=True,
    )
    require(
        profile.get('learning_goal') == profile_patch['learning_goal'],
        'Profile PATCH did not persist the learning goal.',
    )
    print(f'PASS PATCH /api/profile/ ({status_code})')

    diagnostic = agent_data(
        '/api/diagnostic/evaluate/',
        method='POST',
        payload={
            'answers': [
                {
                    'question': 'Introduce yourself in English.',
                    'answer': 'My name is Alfie and I live in Cebu.',
                }
            ]
        },
    )
    require(
        len(diagnostic.get('skill_scores', {})) == 5,
        'Diagnostic did not return five skill scores.',
    )

    _, dashboard = request_json('/api/dashboard/', authenticated=True)
    require(
        len(dashboard.get('skill_mastery', [])) == 5,
        'Diagnostic did not create five mastery records.',
    )
    print('PASS diagnostic mastery persistence')

    recommendation = agent_data('/api/curriculum/recommendation/')
    recommended_module = recommendation.get('recommended_module')
    require(recommended_module, 'Recommendation did not return a module.')

    teacher_session = agent_data(
        '/api/teacher/session/',
        method='POST',
        payload={'module_id': recommended_module['id']},
    )
    session_id = teacher_session.get('session_id')
    require(session_id, 'Teacher session did not return a session ID.')

    feedback = agent_data(
        '/api/teacher/feedback/',
        method='POST',
        payload={
            'session_id': session_id,
            'answer': 'Yesterday I go to mall.',
        },
    )
    updated_mastery = feedback.get('updated_mastery', {})
    require(
        updated_mastery.get('score') == feedback.get('score'),
        'Feedback mastery score does not match the session score.',
    )

    plan = agent_data(
        '/api/scheduler/generate-plan/',
        method='POST',
        payload={},
    )
    require(plan.get('plan', {}).get('days'), 'Study plan has no study days.')

    coach = agent_data('/api/coach/summary/')
    require(coach.get('summary'), 'Coach summary is empty.')

    _, dashboard = request_json('/api/dashboard/', authenticated=True)
    require(
        dashboard.get('recommended_module'),
        'Dashboard has no recommended module.',
    )
    require(
        dashboard.get('latest_study_plan'),
        'Dashboard has no latest study plan.',
    )
    require(
        dashboard.get('recent_sessions'),
        'Dashboard has no recent study session.',
    )
    mastery_by_name = {
        item['skill']['name']: int(float(item['score']))
        for item in dashboard.get('skill_mastery', [])
    }
    require(
        mastery_by_name.get(updated_mastery['skill'])
        == updated_mastery['score'],
        'Dashboard does not contain the updated mastery score.',
    )
    print('PASS GET /api/dashboard/ workflow persistence')
    print('Sprint 3 API smoke test passed.')


if __name__ == '__main__':
    try:
        main()
    except SmokeTestError as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        sys.exit(1)
