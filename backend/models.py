from sqlalchemy import Column, String, Float, Integer, Date, Text, DateTime
from sqlalchemy.sql import func
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


class CustomSKU(Base):
    """User-defined SKU catalogue. Users can add/remove SKUs."""
    __tablename__ = "custom_skus"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, default="general")
    unit_cost = Column(Float, default=1.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class HubInventory(Base):
    """Real inventory: actual stock held at each hub per SKU."""
    __tablename__ = "hub_inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    hub_id = Column(String, index=True, nullable=False)
    sku_id = Column(String, index=True, nullable=False)
    quantity = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CoverageCache(Base):
    """Persists computed coverage polygons (GeoJSON) so they survive restarts.
    One row per (centre_id, mode) pair."""
    __tablename__ = "coverage_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    centre_id = Column(String, index=True, nullable=False)
    mode = Column(String, nullable=False)          # "distance" or "time"
    band = Column(String, nullable=False)           # "green", "blue", "red"
    geojson = Column(Text, nullable=False)          # GeoJSON geometry string
    computed_at = Column(DateTime(timezone=True), server_default=func.now())

