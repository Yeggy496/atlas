"""Browser regression: repeat labels follow assignments, not task ids."""
import json
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    problem = context.request.get('http://127.0.0.1:8031/api/templates/academic').json()
    problem['activities'] = [a for a in problem['activities'] if a['name'] in ('高等数学 1', '高等数学 2')]
    for index, activity in enumerate(problem['activities'], 1):
        activity['name'] = f'高等数学（第{index}次）'
    problem['constraints'] = []
    solved = context.request.post('http://127.0.0.1:8031/api/solve', data={'problem': problem, 'reviewed': True}).json()
    assert len(solved['assignments']) == 2
    by_id = sorted(problem['activities'], key=lambda a: a['name'])
    by_assignment = {a['activity_id']: a for a in solved['assignments']}
    # Deliberately place the stored second task first, within each task's time window.
    by_assignment[by_id[1]['id']].update(start=18, end=22)
    by_assignment[by_id[0]['id']].update(start=66, end=70)
    ws = {'problem': problem, 'result': solved, 'previous': [], 'input': '', 'appliedInput': '',
          'mode': 'balanced', 'customWeights': None, 'reviewed': True, 'summary': [], 'warnings': [],
          'inputTab': 'activities', 'view': 'calendar'}
    store = {'schema_version': 1, 'active_scenario': 'academic', 'workspaces': {'academic': ws}}
    context.add_init_script('localStorage.setItem("optiday.workspace.v1",' + json.dumps(json.dumps(store, ensure_ascii=False)) + ')')
    page = context.new_page()
    page.goto('http://127.0.0.1:8031', wait_until='networkidle')
    expect(page.locator('.calendar-event').filter(has_text='高等数学（第1次）')).to_have_count(1)
    expect(page.locator('.calendar-event').filter(has_text='高等数学（第2次）')).to_have_count(1)
    expect(page.get_by_role('button', name='周一 09:00 高等数学（第1次）')).to_be_visible()
    expect(page.get_by_role('button', name='周二 09:00 高等数学（第2次）')).to_be_visible()
    page.get_by_role('button', name='周一 09:00 高等数学（第1次）').click()
    expect(page.get_by_role('dialog', name='高等数学（第1次）')).to_contain_text('任务原名为「高等数学（第2次）」')
    print('PASS: labels follow chronological order; underlying task name is disclosed.')
    browser.close()
