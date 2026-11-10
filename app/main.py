"""FastAPI interface for an intentionally offline delivery simulator."""
from contextlib import asynccontextmanager
import os
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Header, Response
from pydantic import BaseModel, Field
from . import core

class EventBody(BaseModel):
    payload: dict[str, Any]

class DeliveryBody(BaseModel):
    succeeds: bool = Field(description='Simulate success or failure; no real HTTP request is made.')

def create_app(db_path: str | Path | None = None) -> FastAPI:
    path = str(db_path or os.environ.get('WEBHOOK_DB', 'webhooks.sqlite3'))
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        core.initialize(path)
        yield
    application = FastAPI(title='Webhook delivery lab', version='0.1.0', lifespan=lifespan)
    @application.get('/health')
    def health():
        return {'status': 'ok', 'delivery': 'simulated'}
    @application.post('/events', status_code=201)
    def enqueue(body: EventBody, response: Response, idempotency_key: str = Header(min_length=1, max_length=128)):
        try:
            event, created = core.enqueue(path, idempotency_key, body.payload)
        except core.Conflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not created:
            response.status_code = 200
        return event
    @application.get('/events/{event_id}')
    def get(event_id: int):
        result = core.get_event(path, event_id)
        if result is None:
            raise HTTPException(status_code=404, detail='Event not found')
        return result
    @application.post('/events/{event_id}/simulate')
    def simulate(event_id: int, body: DeliveryBody):
        result = core.deliver_one(path, event_id, body.succeeds)
        if result is None:
            raise HTTPException(status_code=404, detail='Event not found')
        return result
    return application

app = create_app()
