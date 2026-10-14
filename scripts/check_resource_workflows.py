"""Exercise real resource/activity forms and the shared CP-SAT API in Chromium.

Start the application, then run:
    python scripts/check_resource_workflows.py --url http://127.0.0.1:8019 --report report.json
No API calls are mocked. Browser data is isolated in a fresh test context.
"""
import argparse
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8019')
parser.add_argument('--proxy')
parser.add_argument('--report')
parser.add_argument('--screenshot-dir')
args = parser.parse_args()
url = args.url.rstrip('/')
report = {'url': url, 'started_at': datetime.now(timezone.utc).isoformat(),
          'checks': [], 'page_errors': [], 'console_errors': [], 'status': 'running'}
launch = {'headless': True}
if args.proxy:
    launch['proxy'] = {'server': args.proxy}


def stored(page, scenario):
    return page.evaluate('(scenario) => JSON.parse(localStorage.getItem("atlas.workspace.v1")).workspaces[scenario]', scenario)


def wait_for_activity(page, scenario, name):
    page.wait_for_function('''({scenario, name}) => JSON.parse(localStorage.getItem('atlas.workspace.v1'))
        ?.workspaces[scenario]?.problem.activities.some(a => a.name === name)''', arg={'scenario': scenario, 'name': name})
    return next(a for a in stored(page, scenario)['problem']['activities'] if a['name'] == name)


def validate_submit(page, dialog, button_name):
    with page.expect_response(lambda response: response.url.endswith('/api/constraints/validate')) as pending:
        dialog.get_by_role('button', name=button_name, exact=True).click()
    response = pending.value
    assert response.status == 200, response.text()
    expect(dialog).not_to_be_visible()
    return response.request.post_data_json


def open_manager(page):
    page.get_by_role('button', name='管理资源', exact=True).click()
    dialog = page.get_by_role('dialog', name='管理资源', exact=True)
    expect(dialog).to_be_visible()
    return dialog


def expand_resource(dialog, name):
    section = dialog.locator('.resource-manager-item').filter(has=page.get_by_text(name, exact=True))
    toggle = section.locator('.resource-manager-toggle')
    if toggle.get_attribute('aria-expanded') != 'true':
        toggle.click()
    return section


def solve_current(page):
    page.get_by_role('checkbox', name='我已检查并确认当前任务与约束', exact=True).check()
    with page.expect_response(lambda response: response.url.endswith('/api/solve'), timeout=120000) as pending:
        page.locator('.optimize-button').click()
    response = pending.value
    assert response.status == 200, response.text()
    result = response.json()
    assert result['status'] in ('FEASIBLE', 'OPTIMAL'), result
    assert result['metrics']['hard_violations'] == 0, result
    return result


def switch_scene(page, label):
    with page.expect_response(lambda response: response.url.endswith('/api/solve'), timeout=120000) as pending:
        page.get_by_role('button', name=label, exact=True).click()
    result = pending.value.json()
    assert result['status'] in ('FEASIBLE', 'OPTIMAL'), result
    assert result['metrics']['hard_violations'] == 0, result


def check_mobile(page, dialog, filename):
    page.set_viewport_size({'width': 390, 'height': 844})
    box = dialog.bounding_box()
    assert box['x'] >= 0 and box['x'] + box['width'] <= 390, box
    assert dialog.evaluate('(el) => el.scrollWidth <= el.clientWidth + 1'), 'dialog has horizontal overflow'
    for field in dialog.locator('input:visible, select:visible').all():
        field_box = field.bounding_box()
        assert field_box['x'] >= 0 and field_box['x'] + field_box['width'] <= 390, field_box
    dialog.get_by_role('button').last.scroll_into_view_if_needed()
    expect(dialog.get_by_role('button').last).to_be_visible()
    if args.screenshot_dir:
        directory = Path(args.screenshot_dir)
        directory.mkdir(parents=True, exist_ok=True)
        dialog.evaluate('(el) => { el.scrollTop = 0; }')
        dialog.screenshot(path=str(directory / filename))
    page.set_viewport_size({'width': 1440, 'height': 1000})


try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        page.set_default_timeout(15000)
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.on('console', lambda message: report['console_errors'].append(message.text)
                if message.type == 'error' and 'status of 422' not in message.text else None)
        validation_requests = []
        page.on('request', lambda request: validation_requests.append(request.post_data_json)
                if request.url.endswith('/api/constraints/validate') else None)
        with page.expect_response(lambda response: response.url.endswith('/api/solve'), timeout=120000) as pending:
            page.goto(url, wait_until='networkidle', timeout=120000)
        assert pending.value.json()['metrics']['hard_violations'] == 0
        report['version'] = page.request.get(url + '/api/health').json()['version']

        switch_scene(page, '智能排课')
        page.get_by_role('button', name='添加活动', exact=True).click()
        dialog = page.get_by_role('dialog', name='添加活动', exact=True)
        dialog.get_by_label('活动名称', exact=True).fill('多资源排课测试')
        expect(dialog.get_by_label('类别', exact=True)).to_have_value('course')
        dialog.get_by_label('时长', exact=True).select_option('4')
        dialog.locator('.editor-resource-settings > summary').click()
        expect(dialog.get_by_role('checkbox', name='占用计算机 2401 班', exact=True)).to_be_checked()
        dialog.get_by_role('checkbox', name='占用张老师', exact=True).check()
        dialog.get_by_role('checkbox', name='候选场地教学楼 A201', exact=True).check()
        dialog.get_by_role('checkbox', name='候选场地计算机实验室', exact=True).check()
        dialog.get_by_label('最低座位数', exact=True).fill('36')
        dialog.get_by_label('场地类型要求', exact=True).select_option('lecture')
        dialog.get_by_label('最早开始', exact=True).select_option('16')
        dialog.get_by_label('最晚结束', exact=True).select_option('32')
        check_mobile(page, dialog, 'resource-activity-mobile-20261014.png')
        validate_submit(page, dialog, '添加并检查约束')
        course = wait_for_activity(page, 'academic', '多资源排课测试')
        assert set(course['resources']) == {'class', 'zhang'}, course
        assert course['room_options'] == ['room1', 'room2'], course
        assert course['required_seats'] == 36 and course['room_type'] == 'lecture', course
        assert course['window_start'] == 16 and course['window_end'] == 32 and course['days'] == [0, 1, 2, 3, 4], course
        expect(page.get_by_role('checkbox', name='我已检查并确认当前任务与约束', exact=True)).not_to_be_checked()
        report['checks'].append('new course stores class + teacher, candidate rooms, seats, room type and weekday time window through real validation')

        page.get_by_role('button', name='编辑活动 多资源排课测试', exact=True).click()
        dialog = page.get_by_role('dialog', name='编辑活动', exact=True)
        validate_submit(page, dialog, '保存修改')
        assert wait_for_activity(page, 'academic', '多资源排课测试') == course
        existing = next(a for a in stored(page, 'academic')['problem']['activities'] if a['id'] == 'db0')
        page.get_by_role('button', name='编辑活动 ' + existing['name'], exact=True).click()
        dialog = page.get_by_role('dialog', name='编辑活动', exact=True)
        validate_submit(page, dialog, '保存修改')
        assert wait_for_activity(page, 'academic', existing['name']) == existing
        report['checks'].append('editing without touching advanced settings preserves every existing activity field including multiple resources and room choices')
        course_result = solve_current(page)
        assignment = next(a for a in course_result['assignments'] if a['activity_id'] == course['id'])
        assert assignment['room_id'] == 'room1', assignment
        report['academic_result'] = {'status': course_result['status'], 'hard_violations': course_result['metrics']['hard_violations'],
                                     'scheduled': len(course_result['assignments']), 'new_course_room': assignment['room_id']}
        report['checks'].append('CP-SAT returns a checked legal course schedule and assigns the matching lecture room')

        dialog = open_manager(page)
        section = expand_resource(dialog, '计算机 2401 班')
        expect(section.get_by_role('button', name='删除资源', exact=True)).to_be_disabled()
        expect(section.get_by_text('正在使用，暂不能删除', exact=True)).to_be_visible()
        section = expand_resource(dialog, '教学楼 A201')
        expect(section.get_by_label('资源类型', exact=True)).to_be_disabled()
        expect(section.get_by_role('button', name='删除资源', exact=True)).to_be_disabled()
        report['checks'].append('resources referenced by activities and candidate rooms cannot be removed or changed away from room type')

        dialog.get_by_role('button', name='新增资源', exact=True).click()
        count = len(validation_requests)
        dialog.get_by_role('button', name='保存资源', exact=True).click()
        expect(dialog.get_by_role('alert')).to_contain_text('请输入资源名称')
        assert len(validation_requests) == count
        section = dialog.locator('.resource-manager-item.expanded')
        section.get_by_label('资源名称', exact=True).fill('备用设备测试')
        section.get_by_label('资源类型', exact=True).select_option('equipment')
        section.get_by_label('同时可用数量', exact=True).fill('0')
        dialog.get_by_role('button', name='保存资源', exact=True).click()
        expect(dialog.get_by_role('alert')).to_contain_text('1 到 100 的整数')
        assert len(validation_requests) == count
        section.get_by_label('同时可用数量', exact=True).fill('2')
        check_mobile(page, dialog, 'resource-manager-mobile-20261014.png')
        validate_submit(page, dialog, '保存资源')
        page.wait_for_function('''() => JSON.parse(localStorage.getItem('atlas.workspace.v1'))
            .workspaces.academic.problem.resources.some(r => r.name === '备用设备测试')''')
        report['checks'].append('blank resource names and zero quantities are blocked inline without reaching the backend; valid additions are persisted')
        dialog = open_manager(page)
        section = expand_resource(dialog, '备用设备测试')
        expect(section.get_by_role('button', name='删除资源', exact=True)).to_be_enabled()
        section.get_by_role('button', name='删除资源', exact=True).click()
        validate_submit(page, dialog, '保存资源')
        page.wait_for_function('''() => !JSON.parse(localStorage.getItem('atlas.workspace.v1'))
            .workspaces.academic.problem.resources.some(r => r.name === '备用设备测试')''')
        report['checks'].append('unused resources can be removed and the real validated problem no longer contains them')

        dialog = open_manager(page)
        dialog.get_by_role('button', name='新增资源', exact=True).click()
        section = dialog.locator('.resource-manager-item.expanded')
        section.get_by_label('资源名称', exact=True).fill('仅约束引用设备')
        section.get_by_label('资源类型', exact=True).select_option('equipment')
        validate_submit(page, dialog, '保存资源')
        page.wait_for_function('''() => JSON.parse(localStorage.getItem('atlas.workspace.v1'))
            .workspaces.academic.problem.resources.some(r => r.name === '仅约束引用设备')''')
        resource = next(r for r in stored(page, 'academic')['problem']['resources'] if r['name'] == '仅约束引用设备')
        page.get_by_role('button', name='添加约束', exact=True).click()
        dialog = page.get_by_role('dialog', name='添加约束', exact=True)
        dialog.get_by_label('约束说明', exact=True).fill('设备维护时间')
        dialog.get_by_label('作用对象', exact=True).select_option(resource['id'])
        validate_submit(page, dialog, '保存约束')
        dialog = open_manager(page)
        section = expand_resource(dialog, '仅约束引用设备')
        expect(section.get_by_role('button', name='删除资源', exact=True)).to_be_disabled()
        expect(section.get_by_text('0 项活动、1 条约束正在使用此资源。', exact=True)).to_be_visible()
        expect(section.get_by_label('资源不可用时间')).to_contain_text('周三 14:00–16:00')
        dialog.get_by_role('button', name='关闭', exact=True).click()
        report['checks'].append('a resource referenced only by a constraint is protected and its real unavailable time is displayed')

        switch_scene(page, '实验室调度')
        page.get_by_role('button', name='添加活动', exact=True).click()
        dialog = page.get_by_role('dialog', name='添加活动', exact=True)
        dialog.get_by_label('活动名称', exact=True).fill('双设备并行实验测试')
        expect(dialog.get_by_label('类别', exact=True)).to_have_value('experiment')
        dialog.get_by_label('时长', exact=True).select_option('4')
        dialog.locator('.editor-resource-settings > summary').click()
        dialog.get_by_role('checkbox', name='占用离心机 · 2 台', exact=True).check()
        dialog.get_by_label('离心机 · 2 台需求数量', exact=True).fill('2')
        dialog.get_by_role('checkbox', name='候选场地基础实验室', exact=True).check()
        dialog.get_by_label('最低座位数', exact=True).fill('4')
        dialog.get_by_label('场地类型要求', exact=True).select_option('general')
        dialog.get_by_label('最早开始', exact=True).select_option('18')
        dialog.get_by_label('最晚结束', exact=True).select_option('34')
        validate_submit(page, dialog, '添加并检查约束')
        experiment = wait_for_activity(page, 'lab', '双设备并行实验测试')
        assert set(experiment['resources']) == {'teamA', 'centrifuge'}, experiment
        assert experiment['demands'] == {'centrifuge': 2}, experiment
        assert experiment['room_options'] == ['lab2'] and experiment['required_seats'] == 4, experiment
        page.get_by_role('button', name='编辑活动 双设备并行实验测试', exact=True).click()
        dialog = page.get_by_role('dialog', name='编辑活动', exact=True)
        validate_submit(page, dialog, '保存修改')
        assert wait_for_activity(page, 'lab', '双设备并行实验测试') == experiment
        lab_result = solve_current(page)
        assignment = next(a for a in lab_result['assignments'] if a['activity_id'] == experiment['id'])
        assert assignment['room_id'] == 'lab2', assignment
        report['lab_result'] = {'status': lab_result['status'], 'hard_violations': lab_result['metrics']['hard_violations'],
                               'scheduled': len(lab_result['assignments']), 'new_experiment_room': assignment['room_id']}
        report['checks'].append('laboratory task demands two centrifuges and a matching lab; quantity survives editing and CP-SAT independently validates its schedule')

        page.get_by_role('button', name='添加活动', exact=True).click()
        dialog = page.get_by_role('dialog', name='添加活动', exact=True)
        dialog.get_by_label('活动名称', exact=True).fill('边界输入测试')
        dialog.locator('.editor-resource-settings > summary').click()
        dialog.get_by_label('最早开始', exact=True).select_option('42')
        dialog.get_by_label('最晚结束', exact=True).select_option('42')
        count = len(validation_requests)
        dialog.get_by_role('button', name='添加并检查约束', exact=True).click()
        expect(dialog.get_by_role('alert')).to_contain_text('允许时间范围需能容纳完整活动')
        assert len(validation_requests) == count
        dialog.get_by_label('最早开始', exact=True).select_option('16')
        dialog.get_by_label('最晚结束', exact=True).select_option('44')
        dialog.get_by_label('最低座位数', exact=True).fill('12')
        dialog.get_by_role('button', name='添加并检查约束', exact=True).click()
        expect(dialog.get_by_role('alert')).to_contain_text('至少选择一个候选场地')
        assert len(validation_requests) == count
        dialog.get_by_role('checkbox', name='候选场地基础实验室', exact=True).check()
        dialog.get_by_role('checkbox', name='占用离心机 · 2 台', exact=True).check()
        dialog.get_by_label('离心机 · 2 台需求数量', exact=True).fill('0')
        dialog.get_by_role('button', name='添加并检查约束', exact=True).click()
        expect(dialog.get_by_role('alert')).to_contain_text('需求数量需为 1 到 100 的整数')
        assert len(validation_requests) == count
        dialog.get_by_role('button', name='关闭', exact=True).click()
        report['checks'].append('invalid windows, room requirements without a candidate, and zero equipment demand are rejected with actionable inline errors')
        report['checks'].append('resource and activity dialogs fit a 390 px phone with reachable save buttons and no horizontal overflow')
        assert not report['page_errors'], report['page_errors']
        assert not report['console_errors'], report['console_errors']
        browser.close()
        report['status'] = 'passed'
except Exception as error:
    report['status'] = 'failed'
    report['error'] = str(error)
    report['traceback'] = traceback.format_exc()
    raise
finally:
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
