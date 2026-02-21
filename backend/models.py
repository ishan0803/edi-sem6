from sqlalchemy import Column, String, Float, Integer
from database import Base

class FulfillmentCentre(Base):
    __tablename__ = "fulfillment_centres"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    colour_idx = Column(Integer, default=0)
