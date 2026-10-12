"""Three domain fixtures adapt to exactly the same Problem model, never three solvers."""
from .schemas import Activity, Resource, Constraint, Problem


def rule(id, label, type, target='*', **kwargs):
    return Constraint(id=id, label=label, type=type, target=target, source='template', **kwargs)


def life():
    resources = [Resource(id='me', name='我的时间', type='person')]
    activities, constraints = [], []
    for d in range(7):
        activities.append(Activity(id=f'sleep{d}', name='睡眠', duration=16, category='sleep', resources=['me'], days=[d], window_start=0, window_end=16))
        activities.append(Activity(id=f'lunch{d}', name='午餐', duration=1, category='meal', resources=['me'], days=[d], window_start=23, window_end=27))
        activities.append(Activity(id=f'dinner{d}', name='晚餐', duration=1, category='meal', resources=['me'], days=[d], window_start=35, window_end=39))
    for d, name, start in [(0, '高等数学', 18), (1, '大学英语', 20), (2, '数据结构', 18), (3, '计算机实验', 28), (4, '线性代数', 18)]:
        aid = f'class{d}'
        activities.append(Activity(id=aid, name=name, duration=4, category='course', resources=['me'], days=[d]))
        constraints.append(rule(f'fixed{d}', f'{name} · 周{"一二三四五"[d]} {start//2:02}:00，连续 2 小时', 'fixed_time', aid, day=d, start=start))
    for i in range(3):
        activities.append(Activity(id=f'python{i}', name=f'Python 学习 {i+1}', duration=4, category='study', resources=['me']))
        activities.append(Activity(id=f'run{i}', name=f'跑步 {i+1}', duration=2, category='exercise', resources=['me']))
    for i in range(2):
        activities.append(Activity(id=f'math{i}', name=f'高数作业 {i+1}', duration=3, category='homework', resources=['me']))
        constraints.append(rule(f'deadline{i}', '高数作业 · 周三开始前完成', 'deadline', f'math{i}', end=96))
    activities.append(Activity(id='reading', name='自由阅读', duration=2, category='leisure', resources=['me'], optional=True, priority=2))
    constraints += [rule('runpref', '跑步尽量安排在 17:00 以后', 'preferred_window', 'exercise', level='soft', start=34, end=44),
                    rule('rundaily', '跑步分 3 天进行，每天最多 1 次', 'daily_limit', 'exercise', value=1),
                    rule('studywindow', '学习安排在 08:00–22:00', 'time_window', 'study', start=16, end=44),
                    rule('studydaily', 'Python 学习分 3 天进行', 'daily_limit', 'study', value=1)]
    return Problem(scenario='life', name='我的一周', activities=activities, resources=resources, constraints=constraints)


def academic():
    resources = [Resource(id='class', name='计算机 2401 班', type='class'),
                 Resource(id='zhang', name='张老师', type='teacher'), Resource(id='li', name='李老师', type='teacher'),
                 Resource(id='wang', name='王老师', type='teacher'),
                 Resource(id='room1', name='教学楼 A201', type='room', seats=50, room_type='lecture'),
                 Resource(id='room2', name='计算机实验室', type='room', seats=40, room_type='computer')]
    activities, constraints = [], []
    for name, prefix, teacher, count, roomtype in [('高等数学', 'math', 'li', 3, 'lecture'), ('机器学习', 'ml', 'zhang', 2, 'lecture'), ('大学英语', 'eng', 'wang', 2, 'lecture'), ('数据库实验', 'db', 'zhang', 2, 'computer'), ('线性代数', 'linear', 'li', 2, 'lecture')]:
        for i in range(count):
            aid = f'{prefix}{i}'
            activities.append(Activity(id=aid, name=f'{name} {i+1}', duration=4, category='lab' if roomtype == 'computer' else 'course', resources=['class', teacher], room_options=['room1', 'room2'], room_type=roomtype, required_seats=36, days=[0,1,2,3,4], window_start=16, window_end=36))
    constraints += [rule('zhangfriday', '张老师周五下午不可用', 'unavailable', 'zhang', day=4, start=24, end=48),
                    rule('classlunch', '全班 12:00–14:00 午休', 'unavailable', 'class', start=24, end=28),
                    rule('classdaily', '每天最多安排 3 个教学活动', 'daily_limit', '*', value=3),
                    rule('morningpref', '课程尽量安排在上午', 'preferred_window', 'course', level='soft', start=16, end=24),
                    rule('mlconsec', '机器学习 1 与 机器学习 2 连排', 'consecutive', 'ml0', other='ml1')]
    return Problem(scenario='academic', name='计算机 2401 班课表', resources=resources, activities=activities, constraints=constraints)


def lab():
    resources = [Resource(id='teamA', name='实验团队 A', type='team'), Resource(id='teamB', name='实验团队 B', type='team'),
                 Resource(id='spectrometer', name='光谱仪 · 1 台', type='equipment'),
                 Resource(id='centrifuge', name='离心机 · 2 台', type='equipment', capacity=2),
                 Resource(id='lab1', name='分析实验室', type='room', seats=12, room_type='analysis'),
                 Resource(id='lab2', name='基础实验室', type='room', seats=20, room_type='general')]
    activities = []
    for aid, name, duration, team, equipment, roomtype in [('prepA','样品预处理 A',2,'teamA','centrifuge','general'), ('prepB','样品预处理 B',2,'teamB','centrifuge','general'), ('expA','光谱分析 A',4,'teamA','spectrometer','analysis'), ('expB','光谱分析 B',4,'teamB','spectrometer','analysis'), ('dataA','数据整理 A',2,'teamA',None,''), ('dataB','数据整理 B',2,'teamB',None,'')]:
        activities.append(Activity(id=aid, name=name, duration=duration, category='experiment' if equipment else 'study', resources=[team] + ([equipment] if equipment else []), room_options=['lab1','lab2'] if equipment else [], room_type=roomtype, days=[0,1,2,3,4], window_start=18, window_end=36))
    constraints = [rule('preA','先完成预处理 A，再进行光谱分析 A','precedence','prepA',other='expA'),
                   rule('preB','先完成预处理 B，再进行光谱分析 B','precedence','prepB',other='expB'),
                   rule('postA','光谱分析 A 完成后整理数据','precedence','expA',other='dataA'),
                   rule('postB','光谱分析 B 完成后整理数据','precedence','expB',other='dataB')]
    return Problem(scenario='lab', name='实验室本周安排', resources=resources, activities=activities, constraints=constraints)



def meeting():
    """会议/会议室预订：把会议、参会人与共享会议室排到互不冲突的时段。

    与个人日程、排课都不同：这里调度的对象是"预订"，核心冲突是
    共享会议室的容量（人数/是否视频）与参会人（组织者）的时间。
    """
    resources = [Resource(id='room_s', name='小会议室 · 8 人', type='room', seats=8, room_type='meeting'),
                 Resource(id='room_m', name='中会议室 · 20 人', type='room', seats=20, room_type='meeting'),
                 Resource(id='room_v', name='视频会议室 · 12 人', type='room', seats=12, room_type='video'),
                 Resource(id='alice', name='张经理', type='person'),
                 Resource(id='bob', name='李工', type='person')]
    rooms = ['room_s', 'room_m', 'room_v']
    activities = []
    for aid, name, dur, seats, rtype, owner, days, ws, we in [
        ('weekly', '部门周例会', 2, 8, '', 'alice', [0], 16, 24),
        ('review', '产品评审会', 4, 12, '', 'alice', [1, 2, 3], 16, 36),
        ('demo', '客户视频演示', 4, 10, 'video', 'bob', [2, 3, 4], 16, 36),
        ('sharing', '技术分享', 4, 18, '', 'bob', [1, 2], 16, 36),
        ('interview', '新人面试', 2, 4, '', 'alice', [1, 2, 3], 18, 34),
        ('sync', '跨组同步会', 2, 6, '', 'bob', [0, 1, 2, 3, 4], 16, 36)]:
        activities.append(Activity(id=aid, name=name, duration=dur, category='meeting', resources=[owner],
                                   room_options=rooms, required_seats=seats, room_type=rtype,
                                   days=days, window_start=ws, window_end=we))
    constraints = [rule('weeklyfixed', '部门周例会 · 周一 10:00', 'fixed_time', 'weekly', day=0, start=20),
                   rule('nobook', '12:00–13:00 不安排会议', 'unavailable', 'meeting', start=24, end=26),
                   rule('morning', '会议尽量安排在上午', 'preferred_window', 'meeting', level='soft', start=16, end=24),
                   rule('cap', '每天最多 3 场会议', 'daily_limit', '*', value=3)]
    return Problem(scenario='meeting', name='本周会议室预订', resources=resources, activities=activities, constraints=constraints)


def production():
    """生产排程：带多道工序的工单排到共享机台。

    每个工单由 group/op_index 串成"切削加工 -> 装配 -> 质检"的工序链，
    切削工序可在两台数控机床中任选一台——这是纯个人日程无法表达的模型。
    """
    resources = [Resource(id='mill1', name='数控机床 1 号', type='machine'),
                 Resource(id='mill2', name='数控机床 2 号', type='machine'),
                 Resource(id='assembly', name='装配工位', type='machine'),
                 Resource(id='inspect', name='质检工位', type='machine')]
    mills = ['mill1', 'mill2']
    activities, constraints = [], []
    for job, label, cut, asm, qc, due in [
        ('jobA', '工单 A · 轴承座', 4, 2, 2, 96),
        ('jobB', '工单 B · 连接件', 2, 2, 2, 120),
        ('jobC', '工单 C · 法兰盘', 4, 4, 2, 144)]:
        days = [0, 1, 2, 3, 4]
        activities += [
            Activity(id=f'{job}_cut', name=f'{label} · 切削加工', duration=cut, category='operation', resources=[],
                     room_options=mills, group=job, op_index=0, days=days, window_start=16, window_end=44),
            Activity(id=f'{job}_asm', name=f'{label} · 装配', duration=asm, category='operation', resources=['assembly'],
                     group=job, op_index=1, days=days, window_start=16, window_end=44),
            Activity(id=f'{job}_qc', name=f'{label} · 质检', duration=qc, category='operation', resources=['inspect'],
                     group=job, op_index=2, days=days, window_start=16, window_end=44)]
        constraints.append(rule(f'due_{job}', f'{label} · 需在第 {due // 48 + 1} 天结束前完工', 'deadline', f'{job}_qc', end=due))
    constraints.append(rule('workpref', '工序尽量安排在白天 08:00–18:00', 'preferred_window', 'operation', level='soft', start=16, end=36))
    return Problem(scenario='production', name='本周生产工单排程', resources=resources, activities=activities, constraints=constraints)


ADAPTERS = {'life': life, 'academic': academic, 'lab': lab, 'meeting': meeting, 'production': production}
