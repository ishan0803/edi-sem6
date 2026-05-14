from sqlalchemy import Column, String, Float, Integer, Date, Text
from database import Base

class FulfillmentCentre(Base):
    __tablename__ = "fulfillment_centres"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    colour_idx = Column(Integer, default=0)


class StockRecord(Base):
    """Synthetic / uploaded stock snapshot per store per SKU per day."""
    __tablename__ = "stock_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(String, index=True, nullable=False)
    article_id = Column(String, index=True, nullable=False)
    article_description = Column(Text, default="")
    stock_qty = Column(Integer, default=0)
    date = Column(String, nullable=False)


class OrderRecord(Base):
    """Synthetic / uploaded order history per store per SKU per day."""
    __tablename__ = "order_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(String, index=True, nullable=False)
    article_id = Column(String, index=True, nullable=False)
    order_qty = Column(Integer, default=0)
    unique_customers = Column(Integer, default=0)
    order_date = Column(String, nullable=False)
