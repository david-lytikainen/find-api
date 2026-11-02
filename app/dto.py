from pydantic import BaseModel, Field, field_validator


class LocationInput(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ThingLocationInput(LocationInput):
    force_duplicate: bool = False
    description: str = Field(min_length=1, max_length=30)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Add a short description.")
        return value


class ThingInput(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    archived: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Add a name.")
        return value


class VoteInput(BaseModel):
    delta: int = Field(ge=-2, le=2)


class CommentInput(BaseModel):
    report_id: int | None = Field(default=None, ge=1)
    body: str = Field(min_length=1, max_length=500)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Add a comment.")
        return value


class LoginInput(BaseModel):
    email: str
    password: str
