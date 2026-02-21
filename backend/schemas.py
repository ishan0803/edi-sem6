from pydantic import BaseModel

class CentreBase(BaseModel):
    name: str
    lat: float
    lon: float

class CentreCreate(CentreBase):
    pass

class CentreResponse(CentreBase):
    id: str
    colour_idx: int

    class Config:
        from_attributes = True
