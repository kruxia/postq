from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, validator

from . import fields


class Model(BaseModel):
    def dict(self, exclude_none=True, **kwargs):
        return super().dict(exclude_none=exclude_none, **kwargs)


class Job(Model):
    id: UUID = Field(default=None)
    qname: str = Field(default=None)
    retries: int = Field(default=1)
    queued: datetime = Field(default=None)
    scheduled: datetime = Field(default=None)
    status: str = Field(default=fields.JobStatus.queued.name)
    tasks: dict = Field(default_factory=dict)
    data: dict = Field(default_factory=dict)

    @validator('status')
    def validate_job_status(cls, val, values, **kwargs):
        if val not in fields.JobStatus.__members__.keys():
            raise ValidationError(
                f'value must be one of {list(fields.JobStatus.__members__.keys())}'
            )
        return val


class JobLog(Model):
    id: UUID
    qname: str = Field(default=None)
    retries: int
    queued: datetime
    scheduled: datetime
    status: str
    tasks: dict
    data: dict
    logged: datetime = Field(default=None)
    errors: dict = Field(default_factory=dict)

    @validator('status')
    def validate_job_status(cls, val, values, **kwargs):
        if val not in fields.JobStatus.__members__.keys():
            raise ValidationError(
                f'value must be one of {list(fields.JobStatus.__members__.keys())}'
            )
        return val
