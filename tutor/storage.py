import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return uuid.uuid4().hex


class TurnBusy(RuntimeError):
    pass


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS students(id TEXT PRIMARY KEY,name TEXT NOT NULL,basics TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,student_id TEXT NOT NULL REFERENCES students(id),problem_id TEXT NOT NULL,created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS interactions(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions(id),created TEXT NOT NULL,attempt TEXT NOT NULL,response TEXT,trace TEXT NOT NULL,status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS observations(id TEXT PRIMARY KEY,student_id TEXT NOT NULL REFERENCES students(id),interaction_id TEXT NOT NULL REFERENCES interactions(id),concept TEXT NOT NULL,kind TEXT NOT NULL,quote TEXT NOT NULL,note TEXT NOT NULL,created TEXT NOT NULL,status TEXT NOT NULL,help_level INTEGER);
            CREATE TABLE IF NOT EXISTS materials(id TEXT PRIMARY KEY,kind TEXT NOT NULL,body TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS session_owner ON sessions(student_id);
            CREATE INDEX IF NOT EXISTS turn_session ON interactions(session_id,created);
            CREATE INDEX IF NOT EXISTS observation_owner ON observations(student_id,concept);
            """)

    @contextmanager
    def turn_guard(self):
        """Candado del sistema operativo: se libera incluso al cerrar abruptamente el proceso."""
        import os
        handle = open(self.path.with_suffix(".turn.lock"),"a+b")
        handle.seek(0,2)
        if handle.tell()==0:
            handle.write(b"0"); handle.flush()
        handle.seek(0)
        locked = False
        try:
            try:
                if os.name=="nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:
                raise TurnBusy("Otro proceso está procesando un turno") from None
            locked=True
            yield
        finally:
            if locked:
                handle.seek(0)
                if os.name=="nt":
                    msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
            handle.close()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_student(self, name: str, basics: list[str]):
        student = dict(id=uid(), name=name, basics=basics, created=now())
        with self.connect() as db:
            db.execute("INSERT INTO students VALUES(?,?,?,?)", (student["id"],name,json.dumps(basics),student["created"]))
        return student

    def students(self):
        with self.connect() as db:
            return [dict(r, basics=json.loads(r["basics"])) for r in db.execute("SELECT * FROM students ORDER BY created")]

    def student(self, student_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
            if not row:
                raise KeyError("Estudiante inexistente")
            return dict(row, basics=json.loads(row["basics"]))

    def create_session(self, student_id, problem_id):
        self.student(student_id)
        session = dict(id=uid(),student_id=student_id,problem_id=problem_id,created=now())
        with self.connect() as db:
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", tuple(session.values()))
        return session

    def sessions(self, student_id):
        self.student(student_id)
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM sessions WHERE student_id=? ORDER BY created", (student_id,))]

    def session(self, student_id, session_id, internal=False):
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=? AND student_id=?", (session_id,student_id)).fetchone()
            if not row:
                raise KeyError("Sesión inexistente para este estudiante")
            interactions = []
            for item in db.execute("SELECT * FROM interactions WHERE session_id=? ORDER BY created,id", (session_id,)):
                turn = dict(id=item["id"],created=item["created"],attempt=json.loads(item["attempt"]),
                            response=json.loads(item["response"]) if item["response"] else None,status=item["status"])
                if internal:
                    turn["trace"] = json.loads(item["trace"])
                interactions.append(turn)
            return dict(row, interactions=interactions)

    def record(self, interaction_id, session_id, attempt, response, trace, status, observation=None, level=None):
        timestamp = now()
        with self.connect() as db:
            db.execute("INSERT INTO interactions VALUES(?,?,?,?,?,?,?)", (interaction_id,session_id,timestamp,
                json.dumps(attempt,ensure_ascii=False),json.dumps(response,ensure_ascii=False) if response else None,json.dumps(trace,ensure_ascii=False),status))
            if observation:
                student_id = db.execute("SELECT student_id FROM sessions WHERE id=?", (session_id,)).fetchone()[0]
                db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?)", (uid(),student_id,interaction_id,
                    observation.concept,observation.kind,observation.quote,observation.note,timestamp,"provisional",level))
                # Confirmación: evidencia consistente en DOS problemas distintos; nunca una sola respuesta.
                count = db.execute("""SELECT COUNT(DISTINCT s.problem_id) FROM observations o
                    JOIN interactions i ON i.id=o.interaction_id JOIN sessions s ON s.id=i.session_id
                    WHERE o.student_id=? AND o.concept=? AND o.kind=?""", (student_id,observation.concept,observation.kind)).fetchone()[0]
                if count >= 2:
                    db.execute("UPDATE observations SET status='confirmado' WHERE student_id=? AND concept=? AND kind=?", (student_id,observation.concept,observation.kind))

    def profile(self, student_id):
        student = self.student(student_id)
        with self.connect() as db:
            observations = [dict(r) for r in db.execute("SELECT * FROM observations WHERE student_id=? ORDER BY created", (student_id,))]
        return dict(student_id=student_id, declared_basics=student["basics"], observations=observations)
