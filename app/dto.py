from pydantic import BaseModel, Field, field_validator


class LocationInput(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class WaterReportInput(LocationInput):
    force_duplicate: bool = False
    description: str = Field(min_length=1, max_length=30)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Add a short description.")
        return value


class VoteInput(BaseModel):
    delta: int = Field(ge=-2, le=2)
