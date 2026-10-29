"""Five-scenario browser regression for repeated-activity display labels.

The test reverses interchangeable synthetic assignments deliberately. It does
not change any existing user workspace and does not call a model.
"""
from copy import deepcopy
import json
from playwright.sync_api import sync_playwright, expect

BASE = 'http://127.0.0.1:8031'
CASES = [
    ('life', '跑步', ['跑步1', '跑步2', '跑步3']),
    ('academic', '高等数学', ['高等数学（第1次）', '高等数学（第2次）', '高等数学（第3次）']),
    ('lab', '样品检测', ['样品检测 1', '样品检测 2', '样品检测 3']),
    ('meeting', '复盘会议', ['复盘会议第一次', '复盘会议第二次', '复盘会议第三次']),
    ('production', '设备巡检', ['设备巡检（第1次）', '设备巡检（第2次）', '设备巡检（第3次）']),
]

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for scene, name, names in CASES:
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        problem = context.request.get(f'{BASE}/api/templates/{scene}').json()
        example = problem['activities'][0]
        problem['activities'] = []
        problem['constraints'] = []
        for i, title in enumerate(names):
            activity = deepcopy(example)
            activity.update(id=f'repeat_{i}', name=title, duration=2, category='test_repeated',
                            resources=[], demands={}, room_options=[], required_seats=0, room_type='',
                            days=[0, 1, 2, 3, 4], window_start=16, window_end=36,
                            optional=False, priority=5, group=None, op_index=0)
            problem['activities'].append(activity)
            problem['constraints'].append({'id': f'preference_{i}', 'type': 'preferred_window',
                'label': '尽量上午', 'target': activity['id'], 'level': 'soft', 'day': None,
                'start': 16, 'end': 24, 'other': None, 'value': 0, 'source': 'test'})
        solved = context.request.post(f'{BASE}/api/solve', data={'problem': problem, 'reviewed': True}).json()
        assert solved['status'] in ('OPTIMAL', 'FEASIBLE') and len(solved['assignments']) == 3
        by_id = {a['activity_id']: a for a in solved['assignments']}
        for index, start in enumerate([114, 66, 18]):
            by_id[f'repeat_{index}'].update(start=start, end=start + 2, room_id=None)
        ws = {'problem': problem, 'result': solved, 'previous': [], 'input': '', 'appliedInput': '',
              'mode': 'balanced', 'customWeights': None, 'reviewed': True, 'summary': [], 'warnings': [],
              'inputTab': 'activities', 'view': 'calendar'}
        store = {'schema_version': 1, 'active_scenario': scene, 'workspaces': {scene: ws}}
        context.add_init_script('localStorage.setItem("optiday.workspace.v1",' + json.dumps(json.dumps(store, ensure_ascii=False)) + ')')
        page = context.new_page()
        page.goto(BASE, wait_until='networkidle')
        for day, number in [('周一', 1), ('周二', 2), ('周三', 3)]:
            expect(page.get_by_role('button', name=f'{day} 09:00 {name}（第{number}次）')).to_be_visible()
        page.get_by_role('button', name=f'周一 09:00 {name}（第1次）').click()
        dialog = page.get_by_role('dialog', name=f'{name}（第1次）')
        expect(dialog).to_contain_text(f'任务原名为「{names[2]}」')
        dialog.get_by_role('button', name='关闭').click()
        page.get_by_role('button', name='清单', exact=True).click()
        expect(page.get_by_role('button', name=f'周一 09:00 {name}（第1次）')).to_be_visible()
        if scene == 'life':
            with page.expect_request('**/api/export/xlsx') as request_info:
                page.get_by_role('button', name='导出 Excel').click()
            request_data = request_info.value.post_data_json
            assert [a['name'] for a in request_data['problem']['activities']] == [
                f'{name}（第3次）', f'{name}（第2次）', f'{name}（第1次）']
            assert [a['id'] for a in request_data['problem']['activities']] == ['repeat_0', 'repeat_1', 'repeat_2']
        stored = page.evaluate(f'JSON.parse(localStorage.getItem("optiday.workspace.v1")).workspaces.{scene}.problem.activities.map(a => a.name)')
        assert stored == names, 'Presentation must not rewrite the underlying tasks'
        print(f'PASS {scene}: chronological labels in calendar, detail and list; source unchanged', flush=True)
        context.close()
        if scene == 'life':
            linked = deepcopy(problem)
            linked['constraints'].append({'id': 'order', 'type': 'precedence', 'label': '第3次必须在第1次前',
                'target': 'repeat_2', 'other': 'repeat_0', 'level': 'hard', 'day': None,
                'start': 0, 'end': 48, 'value': 0, 'source': 'test'})
            linked_ws = {**ws, 'problem': linked}
            linked_store = {'schema_version': 1, 'active_scenario': scene, 'workspaces': {scene: linked_ws}}
            linked_context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            linked_context.add_init_script('localStorage.setItem("optiday.workspace.v1",' + json.dumps(json.dumps(linked_store, ensure_ascii=False)) + ')')
            linked_page = linked_context.new_page()
            linked_page.goto(BASE, wait_until='networkidle')
            expect(linked_page.get_by_role('button', name='周一 09:00 跑步3')).to_be_visible()
            expect(linked_page.get_by_role('button', name='周三 09:00 跑步1')).to_be_visible()
            print('PASS: explicitly linked tasks keep their original identities', flush=True)
            linked_context.close()
    browser.close()
