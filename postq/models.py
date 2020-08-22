from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class Model(BaseModel):
    def dict(self, exclude_none=True, **kwargs):
        return super().dict(exclude_none=exclude_none, **kwargs)


class Job(Model):
    id: UUID = Field(default=None)
    qname: str = Field(default=None)
    retries: int = Field(default=1)
    queued: datetime = Field(default=None)
    scheduled: datetime = Field(default=None)
    tasks: dict = Field(default_factory=dict)
    data: dict = Field(default_factory=dict)


class JobLog(Model):
    id: UUID
    qname: str
    retries: int
    queued: datetime
    scheduled: datetime
    tasks: dict
    data: dict
    completed: datetime = Field(default=None)
    errors: dict = Field(default_factory=dict)
