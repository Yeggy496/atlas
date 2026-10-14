import json
import os
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.orm import declarative_base, Session

DB_PATH=Path(os.getenv('ATLAS_DB_PATH',str(Path(__file__).resolve().parents[2]/'atlas.db'))).resolve()
engine=create_engine('sqlite:///'+DB_PATH.as_posix(),connect_args={'check_same_thread':False})
Base=declarative_base()


def server_history_enabled():
    """Legacy shared history is opt-in for trusted, single-user local installs.

    Public deployments have no authentication or user isolation. Their history
    belongs in each browser, so never read or store submitted problems here.
    """
    return os.getenv('ATLAS_SERVER_HISTORY', '').strip().lower() == 'true'


class SolveRun(Base):
    __tablename__='solve_runs'
    id=Column(String,primary_key=True)
    created_at=Column(String,nullable=False)
    problem=Column(Text,nullable=False)
    result=Column(Text,nullable=False)


def init_db():
    if server_history_enabled():
        Base.metadata.create_all(engine)


def save_run(id,problem,result):
    if not server_history_enabled():
        return
    with Session(engine) as session:
        session.add(SolveRun(id=id,created_at=datetime.now(timezone.utc).isoformat(),problem=json.dumps(problem,ensure_ascii=False),result=json.dumps(result,ensure_ascii=False)))
        session.commit()


def recent_runs():
    if not server_history_enabled():
        return []
    with Session(engine) as session:
        rows=session.query(SolveRun).order_by(SolveRun.created_at.desc()).limit(12).all()
        return [{'id':x.id,'created_at':x.created_at,'problem':json.loads(x.problem),'result':json.loads(x.result)} for x in rows]
