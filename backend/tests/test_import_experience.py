"""Imports preserve real spreadsheet values and disclose every appended row."""
from datetime import datetime, time
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook
import pytest

from app.adapters import ADAPTERS
from app.importer import extract_text, import_table, parse_clock
from app.llm.providers import DemoProvider
from app.main import app
from app.schemas import Problem, Resource


def blank(scenario='life', resources=None):
    template = ADAPTERS[scenario]()
    return Problem(scenario=scenario, name='我的计划', activities=[],
                   resources=resources if resources is not None else template.resources)


def csv_row(resources='me', day='3', start='19:00', name='会议', minutes='60'):
    return f'name,duration_minutes,day,start,resources\n{name},{minutes},{day},{start},{resources}\n'.encode('utf-8')


@pytest.mark.parametrize('value,expected', [
    (time(19, 0), 38), (time(19, 30), 39),
    (datetime(2026, 10, 14, 19, 30), 39),
    ('19:00:00', 38), ('9:30:00.000', 19), (19 / 24, 38), (0.0, 0),
])
def test_excel_clock_representations_keep_exact_half_hours(value, expected):
    assert parse_clock(value) == expected


@pytest.mark.parametrize('value', [time(19, 15), '19:15:00', '19:00:01',
                                  '19:30:00.001', '24:00', 'not-time', 0.99,
                                  float('nan'), float('inf'), 0.999999999999])
def test_unsupported_clock_precision_is_not_rounded(value):
    with pytest.raises(ValueError, match='半小时'):
        parse_clock(value)


def test_native_xlsx_time_cell_imports_through_the_public_endpoint():
    workbook = Workbook()
    workbook.active.append(['活动名称', '时长（分钟）', '星期', '开始时间', '资源名称'])
    workbook.active.append(['晚间讨论', 90, '周三', time(19, 30), '我的时间'])
    output = BytesIO()
    workbook.save(output)
    with TestClient(app) as client:
        response = client.post('/api/import',
            data={'problem_json': blank().model_dump_json()},
            files={'file': ('meeting.xlsx', output.getvalue())})
    assert response.status_code == 200
    data = response.json()
    assert data['added_count'] == 1 and data['requires_review'] is True
    assert data['problem']['activities'][0]['duration'] == 3
    assert data['problem']['activities'][0]['resources'] == ['me']
    assert data['problem']['constraints'][0]['start'] == 39


def test_import_clock_error_names_the_bad_row_and_leaves_the_input_unchanged():
    problem = blank()
    content = csv_row(start='19:15:00')
    with pytest.raises(ValueError, match='第 2 行.*半小时'):
        import_table(problem, 'tasks.csv', content)
    assert problem.activities == [] and problem.constraints == []


@pytest.mark.parametrize('scenario,expected', [('life', 'me'), ('academic', 'class'),
    ('lab', 'teamA'), ('meeting', 'room_m'), ('production', 'mill1')])
def test_missing_resource_uses_an_existing_scenario_default(scenario, expected):
    data = import_table(blank(scenario), 'tasks.csv', csv_row(resources=''))
    assert data['problem']['activities'][0]['resources'] == [expected]


def test_custom_resource_names_and_ids_map_to_the_current_model():
    resources = [Resource(id='student_1', name='我的安排'),
                 Resource(id='device_1', name='电脑', type='equipment')]
    data = import_table(blank(resources=resources), 'tasks.csv',
                        csv_row(resources='我的安排|device_1|我的安排'))
    assert data['problem']['activities'][0]['resources'] == ['student_1', 'device_1']


def test_custom_unique_person_is_used_instead_of_a_missing_me_id():
    resources = [Resource(id='person_1', name='我'), Resource(id='room', name='学习室', type='room')]
    data = import_table(blank(resources=resources), 'tasks.csv', csv_row(resources=''))
    assert data['problem']['activities'][0]['resources'] == ['person_1']


@pytest.mark.parametrize('cell,phrase', [('老师', '重名'), ('不存在', '找不到资源'), ('', '无法唯一确定')])
def test_ambiguous_or_unknown_resource_is_a_row_aware_error(cell, phrase):
    resources = [Resource(id='p1', name='老师'), Resource(id='p2', name='老师')]
    with pytest.raises(ValueError, match=f'第 2 行.*{phrase}'):
        import_table(blank(resources=resources), 'tasks.csv', csv_row(resources=cell))


def test_a_repeated_import_appends_with_a_warning_instead_of_silently_dropping_rows():
    first = import_table(blank(), 'tasks.csv', csv_row())
    second = import_table(Problem.model_validate(first['problem']), 'tasks.csv', csv_row())
    assert len(second['problem']['activities']) == 2
    assert len({item['id'] for item in second['problem']['activities']}) == 2
    assert second['duplicate_candidates'] == 1
    assert '独立活动追加' in second['warnings'][0]


def test_cross_midnight_import_has_a_clear_error_instead_of_an_unsolvable_task():
    with pytest.raises(ValueError, match='第 2 行.*超过当天 24:00'):
        import_table(blank(), 'tasks.csv', csv_row(start='23:30', minutes='60'))


def test_text_import_preserves_the_tail_beyond_the_old_twenty_thousand_limit():
    text = '活动' * 12_000 + '最后还有一个重要截止日期。'
    data = extract_text('requirements.txt', text.encode('utf-8'))
    assert data['text'] == text
    assert data['original_chars'] == len(text) and data['truncated'] is False
    assert data['parse_limit'] == 4000 and data['chunk_count'] == 7


def test_excessively_expanded_document_is_rejected_explicitly_in_full():
    with pytest.raises(ValueError, match='没有截取或导入部分内容'):
        extract_text('requirements.txt', b'a' * 200_001)


@pytest.mark.parametrize('text,start', [
    ('周三晚上7点有一个会议。', 38), ('周三下午2点有一个会议。', 28),
    ('周三晚上7点半有一个会议。', 39), ('周三19:30有一个会议。', 39),
    ('周三中午12点有一个会议。', 24),
])
def test_offline_parser_respects_explicit_chinese_clock_periods(text, start):
    data = DemoProvider().parse_constraints(blank(), text)
    assert data['problem']['constraints'][0]['start'] == start
    assert data['requires_review'] is True


def test_offline_parser_rejects_fifteen_minutes_without_rounding():
    with pytest.raises(ValueError, match='没有自动四舍五入'):
        DemoProvider().parse_constraints(blank(), '周三晚上7:15有一个会议。')


def test_offline_running_preference_understands_evening_seven():
    data = DemoProvider().parse_constraints(blank(), '每周跑步3次，最好晚上7点以后。')
    preference = next(item for item in data['problem']['constraints'] if item['type'] == 'preferred_window')
    assert preference['start'] == 38


def test_offline_generated_tasks_use_a_custom_person_resource():
    problem = blank(resources=[Resource(id='person_1', name='我')])
    data = DemoProvider().parse_constraints(problem, '周三晚上7点有一个会议。')
    assert data['problem']['activities'][0]['resources'] == ['person_1']
