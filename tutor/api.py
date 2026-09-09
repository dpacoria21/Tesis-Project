from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from pydantic import Field
from tutor.models import (Attempt, PublicProblem, StrictModel, TurnResponse, StudentView,
                          SessionHead, SessionView, ProfileView, RecommendationView, HealthView)
from tutor.provider import ProviderError
from tutor.retrieval import IndexUnavailable
from tutor.service import TutorService


class StudentInput(StrictModel):
    name: str = Field(min_length=1,max_length=100)
    basics: list[str] = Field(default_factory=lambda:["variables","bucles","condicionales","aritmetica"],max_length=30)


class SessionInput(StrictModel):
    problem_id: str = Field(min_length=1,max_length=100)


def create_app(service=None):
    service = service or TutorService()
    @asynccontextmanager
    async def lifespan(app):
        yield
        service.close()
    app = FastAPI(title="Tutor CP",version="0.1.0",description="Prototipo local en español; sin autenticación. Vincular únicamente a localhost.",lifespan=lifespan)
    app.state.service = service

    @app.exception_handler(KeyError)
    async def missing(request: Request, exc: KeyError):
        return JSONResponse(status_code=404,content={"detail":"Recurso inexistente para el estudiante indicado."})

    @app.exception_handler(ProviderError)
    async def provider_error(request: Request, exc: ProviderError):
        return JSONResponse(status_code=503,content={"detail":str(exc),"code":exc.code})

    @app.exception_handler(IndexUnavailable)
    async def index_error(request: Request, exc: IndexUnavailable):
        return JSONResponse(status_code=503,content={"detail":str(exc),"code":"index_unavailable"})

    @app.get("/health",response_model=HealthView)
    def health():
        return dict(status="ok",catalog_problems=len(service.catalog.problems()),index_ready=service.retriever.ready(),
                    llm_configured=service.settings.llm_provider != "disabled" and bool(service.settings.llm_model),
                    execution_enabled=service.settings.execution_enabled)

    @app.post("/students",status_code=201,response_model=StudentView)
    def create_student(body: StudentInput):
        return service.store.create_student(body.name,body.basics)

    @app.get("/students",response_model=list[StudentView])
    def students():
        return service.store.students()

    @app.get("/problems",response_model=list[PublicProblem])
    def problems():
        return [p.public() for p in service.catalog.problems()]

    @app.get("/problems/{problem_id}",response_model=PublicProblem)
    def problem(problem_id: str):
        return service.catalog.problem(problem_id).public()

    @app.post("/students/{student_id}/sessions",status_code=201,response_model=SessionHead)
    def start_session(student_id: str, body: SessionInput):
        return service.start_session(student_id,body.problem_id)

    @app.get("/students/{student_id}/sessions",response_model=list[SessionHead])
    def sessions(student_id: str):
        return service.store.sessions(student_id)

    @app.get("/students/{student_id}/sessions/{session_id}",response_model=SessionView)
    def session(student_id: str,session_id: str):
        return service.store.session(student_id,session_id)

    @app.post("/students/{student_id}/sessions/{session_id}/attempts",response_model=TurnResponse)
    def attempt(student_id: str,session_id: str,body: Attempt):
        return service.turn(student_id,session_id,body)

    @app.get("/students/{student_id}/profile",response_model=ProfileView)
    def profile(student_id: str):
        return service.store.profile(student_id)

    @app.get("/students/{student_id}/recommendations",response_model=RecommendationView)
    def recommendations(student_id: str,goal: str | None=Query(None,max_length=100),max_difficulty: int=Query(3,ge=1,le=5)):
        return service.recommendations(student_id,goal,max_difficulty)

    return app
