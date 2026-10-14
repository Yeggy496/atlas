"""Real-browser reliability checks in isolated profiles; no paid model calls.

Validation, import, repair, and solver requests reach the real backend. The long
text test substitutes only the parser response to check segment retention safely.
Delayed validation requests are held at the browser until the UI guards are read.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

from playwright.sync_api import expect, sync_playwright


WORKSPACE_KEY = 'atlas.workspace.v1'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:5174')
    parser.add_argument('--proxy')
    parser.add_argument('--report')
    args = parser.parse_args()
    url = args.url.rstrip('/')
    report = {'url': url, 'checks': [], 'solves': [], 'page_errors': [],
              'parser_calls': 0, 'paid_model_calls': 0,
              'test_scope': 'isolated browser data; real solver/import/validation/repair; controlled parser only for segment retention'}
    launch = {'headless': True}
    if args.proxy:
        launch['proxy'] = {'server': args.proxy}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch)
        api_context = browser.new_context()
        request = api_context.request

        def get(path):
            response = request.get(url + '/api' + path, timeout=120000)
            assert response.ok, response.text()
            return response.json()

        def post(path, body):
            response = request.post(url + '/api' + path, data=body, timeout=180000)
            assert response.ok, response.text()
            return response.json()

        report['health'] = get('/health')
        template = get('/templates/life')
        task = deepcopy(next(activity for activity in template['activities'] if activity['category'] == 'study'))
        task.update(id='reliability_task', name='可靠性任务', duration=2, days=[0],
                    resources=['me'], demands={}, room_options=[], room_type='',
                    required_seats=0, window_start=16, window_end=40, optional=False,
                    group=None, op_index=0)
        problem = {'scenario': 'life', 'name': '可靠性测试计划', 'week_start': '2026-10-12',
                   'resources': [deepcopy(next(resource for resource in template['resources'] if resource['id'] == 'me'))],
                   'activities': [task], 'constraints': []}
        post('/constraints/validate', problem)
        solved_result = post('/solve', {'problem': problem, 'reviewed': True, 'mode': 'balanced'})
        assert solved_result['status'] in ('OPTIMAL', 'FEASIBLE')
        assert solved_result['metrics']['hard_violations'] == 0
        report['solves'].append({'purpose': 'seed real baseline', 'status': solved_result['status'],
                                 'scheduled': len(solved_result['assignments']),
                                 'hard_violations': solved_result['metrics']['hard_violations']})
        conflict_problem = deepcopy(problem)
        for index, start in enumerate((18, 22)):
            conflict_problem['constraints'].append({'id': f'conflict_{index}',
                'label': f'同一任务固定在不同时间 {index}', 'type': 'fixed_time',
                'target': task['id'], 'level': 'hard', 'day': 0, 'start': start,
                'end': 48, 'other': None, 'value': 0, 'source': 'manual'})
        conflict_result = post('/solve', {'problem': conflict_problem, 'reviewed': True,
                                         'mode': 'balanced', 'previous': solved_result['assignments']})
        assert conflict_result['status'] == 'INFEASIBLE'
        assert conflict_result['repairs'], 'Actual conflict fixture needs a verified repair candidate.'

        def workspace(p=None, result=None, text='', applied=None):
            return {'problem': deepcopy(p or problem), 'result': deepcopy(result),
                'previous': deepcopy(solved_result['assignments']), 'previousProblem': deepcopy(problem),
                'input': text, 'appliedInput': text if applied is None else applied,
                'mode': 'balanced', 'customWeights': None, 'reviewed': True,
                'summary': [], 'warnings': [], 'inputTab': 'activities', 'view': 'calendar'}

        def new_profile(seed=None, viewport=None):
            context = browser.new_context(viewport=viewport or {'width': 1440, 'height': 1050},
                                          timezone_id='Etc/GMT-8')
            # Never let a convenience check accidentally call a paid model.
            context.route('**/api/constraints/parse', lambda route: route.fulfill(
                status=409, json={'detail': '测试已阻止真实模型调用；本用例不需要 AI。'}))
            context.route('**/api/explain', lambda route: route.fulfill(
                status=200, json={'activity_id': task['id'], 'reasons': [], 'narrative': None}))
            if seed is not None:
                payload = json.dumps({'schema_version': 1, 'active_scenario': seed['problem']['scenario'],
                                      'workspaces': {seed['problem']['scenario']: seed}}, ensure_ascii=False)
                context.add_init_script('''try { if (!localStorage.getItem(%s))
                    localStorage.setItem(%s, %s); } catch {}''' % (
                        json.dumps(WORKSPACE_KEY), json.dumps(WORKSPACE_KEY), json.dumps(payload)))
            page = context.new_page()
            page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
            page.goto(url, wait_until='networkidle', timeout=180000)
            expect(page.locator('.busy-status')).to_have_count(0, timeout=180000)
            return context, page

        def stored(page):
            return page.evaluate('JSON.parse(localStorage.getItem("atlas.workspace.v1")).workspaces.life')

        def eventually_saved(page, expression):
            page.wait_for_function('''expression => {
                const workspace = JSON.parse(localStorage.getItem('atlas.workspace.v1'))?.workspaces.life;
                return !!workspace && new Function('workspace', 'return ' + expression)(workspace);
            }''', arg=expression, timeout=10000)

        def solve_ui(page, action):
            with page.expect_response(lambda response: response.url.endswith('/api/solve'), timeout=180000) as pending:
                action()
            response = pending.value
            assert response.ok, response.text()
            result = response.json()
            assert result['status'] in ('OPTIMAL', 'FEASIBLE'), result['status']
            assert result['metrics']['hard_violations'] == 0
            expect(page.locator('.busy-status')).to_have_count(0, timeout=10000)
            report['solves'].append({'purpose': 'UI solve', 'status': result['status'],
                                     'scheduled': len(result['assignments']), 'hard_violations': 0})
            return result

        def import_backup(page, payload):
            page.locator('input[aria-label="选择工作空间备份"]').set_input_files({
                'name': 'reliability-backup.json', 'mimeType': 'application/json',
                'buffer': json.dumps(payload, ensure_ascii=False).encode('utf-8')})
            dialog = page.get_by_role('dialog', name='恢复工作空间备份？', exact=True)
            expect(dialog).to_be_visible(timeout=10000)
            dialog.get_by_role('button', name='确认恢复', exact=True).click()
            expect(dialog).to_have_count(0)

        contexts = []

        def profile(seed=None, viewport=None):
            context, page = new_profile(seed, viewport)
            contexts.append(context)
            return context, page

        def check(name, action):
            start = time.monotonic()
            before = len(contexts)
            try:
                detail = action()
                report['checks'].append({'name': name, 'passed': True,
                                        'seconds': round(time.monotonic() - start, 2), 'detail': detail})
            except Exception as failure:
                evidence = []
                for context in contexts[before:]:
                    for page in context.pages:
                        try:
                            evidence.append({'url': page.url, 'visible_text': page.locator('body').inner_text()[:3500],
                                             'workspace': page.evaluate('localStorage.getItem("atlas.workspace.v1")')})
                        except Exception:
                            pass
                report['checks'].append({'name': name, 'passed': False,
                    'seconds': round(time.monotonic() - start, 2), 'error': str(failure), 'evidence': evidence})
            finally:
                for context in contexts[before:]:
                    context.close()
            print(json.dumps({'check': name, 'passed': report['checks'][-1]['passed']}, ensure_ascii=False), flush=True)

        def welcome():
            _, page = profile()
            welcome_dialog = page.get_by_role('dialog', name='开始安排你的时间', exact=True)
            expect(welcome_dialog).to_be_visible()
            assert stored(page)['problem']['activities'] == [] and stored(page)['result'] is None
            assert stored(page)['input'] == ''
            result = solve_ui(page, lambda: welcome_dialog.get_by_role('button', name='体验完整示例', exact=True).click())
            own_week = stored(page)['problem']['week_start']
            assert len(result['assignments']) > 1
            assert stored(page)['problem']['activities']
            return {'initial_activities': 0, 'explicit_sample_scheduled': len(result['assignments']), 'week_start': own_week}

        check('new visitor starts blank and explicitly chooses a real solved example', welcome)

        def pending_input():
            _, page = profile(workspace(result=solved_result))
            page.get_by_label('自然语言需求', exact=True).fill('新增周三晚上7点会议')
            expect(page.locator('.pending-input')).to_be_visible()
            expect(page.locator('.optimize-button')).to_be_disabled()
            expect(page.locator('.workflow-progress')).to_contain_text('需求尚待识别')
            page.get_by_role('button', name='本次仅使用现有任务与约束', exact=True).click()
            expect(page.locator('.pending-input')).to_have_count(0)
            expect(page.locator('.optimize-button')).to_be_enabled()
            result = solve_ui(page, lambda: page.locator('.optimize-button').click())
            assert len(result['assignments']) == 1
            return 'New text blocks optimization until explicitly interpreted or intentionally excluded.'

        check('unparsed text cannot silently be ignored by Optimize', pending_input)

        def clear_input_undo():
            _, page = profile(workspace(result=solved_result, text='需要保留的输入'))
            before = stored(page)
            page.get_by_role('button', name='清空输入', exact=True).click()
            expect(page.get_by_label('自然语言需求', exact=True)).to_have_value('')
            assert stored(page)['problem'] == before['problem'] and stored(page)['result'] == before['result']
            page.get_by_role('button', name='撤销修改', exact=True).click()
            expect(page.get_by_label('自然语言需求', exact=True)).to_have_value('需要保留的输入')
            eventually_saved(page, 'workspace.input === "需要保留的输入"')
            return 'Clear input preserves the existing model/result and restores text with Undo.'

        check('clear input has a real Undo without losing the plan', clear_input_undo)

        def consecutive_delete_undo():
            two_problem = deepcopy(problem)
            second = deepcopy(task)
            second.update(id='second_reliability_task', name='第二个可靠性任务', days=[2])
            two_problem['activities'].append(second)
            two_result = post('/solve', {'problem': two_problem, 'reviewed': True, 'mode': 'balanced'})
            assert two_result['status'] in ('OPTIMAL', 'FEASIBLE')
            assert two_result['metrics']['hard_violations'] == 0 and len(two_result['assignments']) == 2
            seed = workspace(p=two_problem, result=two_result)
            seed.update(previous=deepcopy(two_result['assignments']), previousProblem=deepcopy(two_problem))
            _, page = profile(seed)
            before = stored(page)
            page.get_by_role('button', name='删除活动 可靠性任务', exact=True).click()
            eventually_saved(page, 'workspace.problem.activities.length === 1')
            after_first = stored(page)
            assert after_first['problem']['activities'][0]['id'] == second['id']
            page.get_by_role('button', name='删除活动 第二个可靠性任务', exact=True).click()
            eventually_saved(page, 'workspace.problem.activities.length === 0')
            undo_button = page.get_by_role('button', name='撤销修改', exact=True)
            expect(undo_button).to_be_visible()
            undo_button.click()
            eventually_saved(page, 'workspace.problem.activities.length === 1')
            assert stored(page) == after_first
            undo_button.click()
            eventually_saved(page, 'workspace.problem.activities.length === 2 && workspace.result !== null')
            assert stored(page) == before, 'Two Undo steps must restore the complete original solved workspace.'
            expect(undo_button).to_have_count(0)
            # The documented session boundary removes Undo without reverting autosaved content.
            page.get_by_role('button', name='删除活动 可靠性任务', exact=True).click()
            eventually_saved(page, 'workspace.problem.activities.length === 1')
            expect(undo_button).to_be_visible()
            page.reload(wait_until='networkidle')
            expect(page.get_by_role('button', name='撤销修改', exact=True)).to_have_count(0)
            assert len(stored(page)['problem']['activities']) == 1
            return 'Two consecutive deletes Undo in reverse order and restore the whole real solved plan; reload clears session Undo while keeping the saved draft.'

        check('consecutive activity deletes can each be undone and session boundaries preserve saved work', consecutive_delete_undo)

        def tabs_latest():
            context, a = profile(workspace(result=solved_result, text='两个标签的原内容'))
            b = context.new_page()
            b.goto(url, wait_until='networkidle')
            a.get_by_label('自然语言需求', exact=True).fill('A 标签最新输入')
            eventually_saved(a, 'workspace.input === "A 标签最新输入"')
            expect(b.locator('.storage-conflict-actions')).to_be_visible()
            b.get_by_role('button', name='资源视图', exact=True).click()
            assert stored(b)['input'] == 'A 标签最新输入', 'Stale view-change autosave overwrote the latest input.'
            b.get_by_role('button', name='打开最新内容', exact=True).click()
            expect(b.get_by_label('自然语言需求', exact=True)).to_have_value('A 标签最新输入')
            expect(b.locator('.storage-conflict-actions')).to_have_count(0)
            b.reload(wait_until='networkidle')
            expect(b.get_by_label('自然语言需求', exact=True)).to_have_value('A 标签最新输入')
            return 'A stale same-scenario tab cannot overwrite newer data via a view switch; latest content can be reopened.'

        check('same-scenario multi-tab autosave protects latest data and opens it on request', tabs_latest)

        def tabs_keep():
            context, a = profile(workspace(result=solved_result, text='原输入'))
            b = context.new_page()
            b.goto(url, wait_until='networkidle')
            a.get_by_label('自然语言需求', exact=True).fill('A 的新输入')
            eventually_saved(a, 'workspace.input === "A 的新输入"')
            expect(b.locator('.storage-conflict-actions')).to_be_visible()
            b.get_by_label('自然语言需求', exact=True).fill('B 决定保留的本地输入')
            assert stored(b)['input'] == 'A 的新输入'
            b.get_by_role('button', name='保留当前编辑', exact=True).click()
            eventually_saved(b, 'workspace.input === "B 决定保留的本地输入"')
            expect(a.locator('.storage-conflict-actions')).to_be_visible()
            assert stored(a)['input'] == 'B 决定保留的本地输入'
            return 'Replacing another tab is an explicit choice; that tab receives its own conflict warning.'

        check('same-scenario local replacement is explicit and warns the other tab', tabs_keep)

        def tabs_clear():
            original = workspace(result=solved_result, text='另一标签清空后仍需保留的内容')
            context, a = profile(original)
            b = context.new_page()
            b.goto(url, wait_until='networkidle')
            a.evaluate('localStorage.clear()')
            expect(b.locator('.storage-conflict-actions')).to_be_visible()
            assert b.evaluate('localStorage.getItem("atlas.workspace.v1")') is None
            expect(b.get_by_label('自然语言需求', exact=True)).to_have_value(original['input'])
            # A stale view-change autosave must also recognize a removed workspace.
            b.get_by_role('button', name='资源视图', exact=True).click()
            assert b.evaluate('localStorage.getItem("atlas.workspace.v1")') is None
            b.get_by_role('button', name='保留当前编辑', exact=True).click()
            eventually_saved(b, 'workspace.input === "另一标签清空后仍需保留的内容"')
            restored = stored(b)
            assert restored['problem'] == original['problem']
            assert restored['result'] == original['result']
            expect(b.locator('.storage-conflict-actions')).to_have_count(0)
            b.reload(wait_until='networkidle')
            expect(b.get_by_label('自然语言需求', exact=True)).to_have_value(original['input'])
            return 'Storage clear in another tab produces an actionable warning; data is restored only by the explicit keep-current choice.'

        check('another tab clearing storage leaves an actionable conflict and current data can be kept', tabs_clear)

        def delayed_date_safe():
            _, page = profile(workspace(result=solved_result))
            held = []
            page.route('**/api/constraints/validate', lambda route: held.append(route))
            with page.expect_request(lambda item: item.url.endswith('/api/constraints/validate')):
                page.get_by_label('选择计划所在周', exact=True).fill('2026-10-28')
            expect(page.get_by_label('选择计划所在周', exact=True)).to_be_disabled()
            expect(page.locator('.scenario-nav').filter(has_text='智能排课')).to_be_disabled()
            expect(page.get_by_role('button', name='添加活动', exact=True)).to_be_disabled()
            route = held.pop()
            response = route.fetch()
            assert response.ok
            route.fulfill(response=response)
            expect(page.locator('.busy-status')).to_have_count(0)
            expect(page.get_by_label('选择计划所在周', exact=True)).to_have_value('2026-10-26')
            eventually_saved(page, 'workspace.problem.week_start === "2026-10-26"')
            return 'Date validation seals global mutation controls until the real validation response returns.'

        check('delayed date validation cannot race a second date or scenario switch', delayed_date_safe)

        def delayed_editor():
            _, page = profile(workspace(result=solved_result))
            held = []
            page.route('**/api/constraints/validate', lambda route: held.append(route))
            page.get_by_role('button', name='添加活动', exact=True).click()
            dialog = page.get_by_role('dialog', name='添加活动', exact=True)
            dialog.get_by_placeholder('例如：社团会议、课程复习').fill('延迟保存的新任务')
            with page.expect_request(lambda item: item.url.endswith('/api/constraints/validate')):
                dialog.get_by_role('button', name='添加并检查约束', exact=True).click()
            expect(dialog.get_by_role('button', name='关闭', exact=True)).to_be_disabled()
            expect(page.locator('.scenario-nav').filter(has_text='智能排课')).to_be_disabled()
            page.keyboard.press('Escape')
            expect(dialog).to_be_visible()
            route = held.pop()
            response = route.fetch()
            assert response.ok
            route.fulfill(response=response)
            expect(dialog).to_have_count(0)
            expect(page.get_by_role('heading', name='个人周计划', exact=True)).to_be_visible()
            eventually_saved(page, 'workspace.problem.activities.length === 2')
            assert stored(page)['problem']['scenario'] == 'life'
            return 'Saving dialog cannot close or change scenario while validation is pending; delayed save applies only to its own scene.'

        check('delayed editor save cannot overwrite a newly selected scenario', delayed_editor)

        def backup_baseline():
            _, page = profile(workspace(result=solved_result))
            source = workspace(p=conflict_problem, result=conflict_result, text='冲突备份')
            assert source['result']['assignments'] == [] and len(source['previous']) == 1
            import_backup(page, {'format': 'atlas-workspace', 'version': 1, 'workspace': source})
            eventually_saved(page, 'workspace.result === null && workspace.previous.length === 1')
            restored = stored(page)
            assert restored['previous'] == solved_result['assignments']
            assert restored['previousProblem'] == problem
            assert restored['reviewed'] is False
            return 'An INFEASIBLE backup with empty assignments retains its last real feasible baseline and requires review.'

        check('backup retains previous baseline when the last solve has no assignments', backup_baseline)

        def plan_json():
            _, page = profile(workspace(result=solved_result))
            with page.expect_download() as pending:
                page.get_by_role('button', name='下载计划 JSON', exact=True).click()
            payload = json.loads(Path(pending.value.path()).read_text(encoding='utf-8'))
            assert payload['problem'] == problem and payload['result']['assignments'] == solved_result['assignments']
            import_backup(page, payload)
            eventually_saved(page, 'workspace.result === null && !workspace.reviewed')
            restored = stored(page)
            assert restored['problem'] == problem and restored['previous'] == solved_result['assignments']
            page.reload(wait_until='networkidle')
            assert stored(page)['result'] is None and stored(page)['reviewed'] is False
            return 'The actual downloaded plan JSON restores editable data and previous assignments without importing untrusted approval.'

        check('downloaded plan JSON can be restored through backup import', plan_json)

        def repair_undo():
            _, page = profile(workspace(p=conflict_problem, result=conflict_result))
            before = stored(page)
            with page.expect_response(lambda response: response.url.endswith('/api/repair'), timeout=180000) as pending:
                page.get_by_role('button', name='应用并求解', exact=True).first.click()
            response = pending.value
            assert response.ok, response.text()
            repaired = response.json()
            assert repaired['result']['status'] in ('FEASIBLE', 'OPTIMAL')
            assert repaired['result']['metrics']['hard_violations'] == 0
            eventually_saved(page, 'workspace.problem.constraints.length === 1')
            page.get_by_role('button', name='撤销修改', exact=True).click()
            eventually_saved(page, 'workspace.problem.constraints.length === 2')
            restored = stored(page)
            assert restored['problem'] == before['problem'] and restored['result'] == before['result']
            assert restored['previous'] == before['previous']
            return 'Repair removed one constraint and found a real legal schedule; Undo restores the complete original conflict workspace.'

        check('real repair has a complete Undo', repair_undo)

        def long_text():
            context, page = profile(workspace(result=solved_result))
            text = '需要逐段完整保留的安排。' * 405 + '末尾重要条件：周日18:00以前交作业。'
            assert len(text) > 4000
            page.locator('input[type="file"][accept=".txt,.pdf"]').set_input_files({
                'name': 'long-requirements.txt', 'mimeType': 'text/plain', 'buffer': text.encode('utf-8')})
            expect(page.get_by_label('自然语言需求', exact=True)).to_have_value(text)
            captured = []
            context.unroute('**/api/constraints/parse')

            def parser_response(route):
                payload = route.request.post_data_json
                captured.append(payload['text'])
                report['parser_calls'] += 1
                # Validate the exact unchanged problem through the real backend.
                post('/constraints/validate', payload['problem'])
                route.fulfill(status=200, json={'problem': payload['problem'],
                    'summary': ['测试仅核对分段保留，不评估模型识别准确率。'],
                    'warnings': [], 'provider': 'demo', 'requires_review': True})

            context.route('**/api/constraints/parse', parser_response)
            page.get_by_role('button', name='识别下一段', exact=True).click()
            expect(page.locator('.busy-status')).to_have_count(0)
            remainder = page.get_by_label('自然语言需求', exact=True).input_value()
            assert captured == [text[:4000]] and remainder == text[4000:]
            expect(page.locator('.optimize-button')).to_be_disabled()
            page.get_by_role('button', name='识别约束', exact=True).click()
            expect(page.locator('.busy-status')).to_have_count(0)
            assert ''.join(captured) == text and len(captured) == 2
            assert captured[-1].endswith('末尾重要条件：周日18:00以前交作业。')
            assert stored(page)['reviewed'] is False
            return {'imported_chars': len(text), 'segments': [len(segment) for segment in captured],
                    'tail_preserved': True, 'parser': 'controlled response; real validation; no paid model'}

        check('long text imports and successive parse segments never lose their tail', long_text)

        def repeated():
            _, page = profile(workspace(result=solved_result))
            page.get_by_role('button', name='重复活动 可靠性任务', exact=True).click()
            dialog = page.get_by_role('dialog', name='重复活动 · 可靠性任务', exact=True)
            dialog.get_by_label('周二', exact=True).check()
            dialog.get_by_label('周四', exact=True).check()
            with page.expect_response(lambda response: response.url.endswith('/api/constraints/validate')):
                dialog.get_by_role('button', name='新增 2 项活动', exact=True).click()
            expect(dialog).to_have_count(0)
            eventually_saved(page, 'workspace.problem.activities.length === 3')
            activities = stored(page)['problem']['activities']
            assert len({activity['id'] for activity in activities}) == 3
            assert sorted(activity['days'][0] for activity in activities) == [0, 1, 3]
            page.get_by_label('我已检查并确认当前任务与约束', exact=True).check()
            result = solve_ui(page, lambda: page.locator('.optimize-button').click())
            assert len(result['assignments']) == 3
            assert len({item['activity_id'] for item in result['assignments']}) == 3
            return {'unique_activities': 3, 'scheduled': 3, 'hard_violations': 0}

        check('repeat activity generates distinct IDs and all copies are genuinely solved', repeated)

        def repeat_time_window():
            source_problem = deepcopy(problem)
            source_problem['activities'][0].update(window_start=16, window_end=20)
            source_problem['constraints'] = [
                {'id': 'monday_window', 'label': '周一 08:00–10:00', 'type': 'time_window',
                 'target': task['id'], 'level': 'hard', 'day': 0, 'start': 16, 'end': 20,
                 'other': None, 'value': 0, 'source': 'manual'},
                {'id': 'absolute_deadline', 'label': '周四开始前完成', 'type': 'deadline',
                 'target': task['id'], 'level': 'hard', 'day': None, 'start': 0, 'end': 144,
                 'other': None, 'value': 0, 'source': 'manual'},
            ]
            one = post('/solve', {'problem': source_problem, 'reviewed': True, 'mode': 'balanced'})
            assert one['status'] in ('OPTIMAL', 'FEASIBLE') and one['metrics']['hard_violations'] == 0
            seed = workspace(p=source_problem, result=one)
            seed.update(previous=deepcopy(one['assignments']), previousProblem=deepcopy(source_problem))
            _, page = profile(seed)
            page.get_by_role('button', name='重复活动 可靠性任务', exact=True).click()
            dialog = page.get_by_role('dialog', name='重复活动 · 可靠性任务', exact=True)
            dialog.get_by_label('周三', exact=True).check()
            with page.expect_response(lambda response: response.url.endswith('/api/constraints/validate')):
                dialog.get_by_role('button', name='新增 1 项活动', exact=True).click()
            expect(dialog).to_have_count(0)
            eventually_saved(page, 'workspace.problem.activities.length === 2')
            copied_problem = stored(page)['problem']
            copied = next(activity for activity in copied_problem['activities'] if activity['id'] != task['id'])
            assert copied['days'] == [2]
            copy_window = next(constraint for constraint in copied_problem['constraints']
                               if constraint['type'] == 'time_window' and constraint['target'] == copied['id'])
            assert (copy_window['day'], copy_window['start'], copy_window['end']) == (2, 16, 20)
            copy_deadline = next(constraint for constraint in copied_problem['constraints']
                                 if constraint['type'] == 'deadline' and constraint['target'] == copied['id'])
            assert copy_deadline['end'] == 144 and copy_deadline['day'] is None
            page.get_by_label('我已检查并确认当前任务与约束', exact=True).check()
            result = solve_ui(page, lambda: page.locator('.optimize-button').click())
            assert len(result['assignments']) == 2
            assert sorted(assignment['start'] // 48 for assignment in result['assignments']) == [0, 2]
            assert all(16 <= assignment['start'] % 48 and assignment['end'] % 48 <= 20
                       for assignment in result['assignments'])
            return {'original_day': 0, 'copied_day': 2, 'time_window': [16, 20],
                    'deadline_kept_absolute': 144, 'scheduled': 2, 'hard_violations': 0}

        check('repeating a dated time window moves it to Wednesday while preserving absolute deadlines', repeat_time_window)

        browser.close()
    report['passed'] = all(check['passed'] for check in report['checks']) and not report['page_errors']
    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = {'passed': report['passed'], 'checks': len(report['checks']),
               'failed_checks': [check['name'] for check in report['checks'] if not check['passed']],
               'page_errors': report['page_errors'], 'paid_model_calls': report['paid_model_calls']}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
