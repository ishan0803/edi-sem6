"""
Demo Data Seeder
================
Populates the database with realistic quick-commerce SKUs and randomized
inventory on first startup. Idempotent — skips if data already exists.
Custom user data is preserved; seed data coexists with user-added items.
"""
import logging
import random
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import CustomSKU, HubInventory, FulfillmentCentre

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demo SKU catalogue — realistic Indian quick-commerce products
# ---------------------------------------------------------------------------
DEMO_SKUS = [
    # Dairy
    {"id": "SKU-MILK500", "name": "Amul Toned Milk 500ml", "category": "dairy", "unit_cost": 27.0},
    {"id": "SKU-CURD400", "name": "Mother Dairy Curd 400g", "category": "dairy", "unit_cost": 35.0},
    {"id": "SKU-BUTTER100", "name": "Amul Butter 100g", "category": "dairy", "unit_cost": 56.0},
    {"id": "SKU-PANEER200", "name": "Amul Fresh Paneer 200g", "category": "dairy", "unit_cost": 90.0},
    # Beverages
    {"id": "SKU-COLA750", "name": "Coca-Cola 750ml", "category": "beverages", "unit_cost": 38.0},
    {"id": "SKU-WATER1L", "name": "Bisleri Water 1L", "category": "beverages", "unit_cost": 20.0},
    {"id": "SKU-JUICE1L", "name": "Real Mango Juice 1L", "category": "beverages", "unit_cost": 99.0},
    # Snacks
    {"id": "SKU-LAYS52", "name": "Lays Classic Salted 52g", "category": "snacks", "unit_cost": 20.0},
    {"id": "SKU-MAGGI70", "name": "Maggi 2-Min Noodles 70g", "category": "snacks", "unit_cost": 14.0},
    {"id": "SKU-BISCUIT150", "name": "Parle-G Biscuits 150g", "category": "snacks", "unit_cost": 10.0},
    # Staples
    {"id": "SKU-ATTA1KG", "name": "Aashirvaad Atta 1kg", "category": "food", "unit_cost": 52.0},
    {"id": "SKU-RICE1KG", "name": "India Gate Basmati 1kg", "category": "food", "unit_cost": 135.0},
    {"id": "SKU-OIL1L", "name": "Fortune Sunflower Oil 1L", "category": "food", "unit_cost": 140.0},
    {"id": "SKU-SUGAR1KG", "name": "Uttam Sugar 1kg", "category": "food", "unit_cost": 45.0},
    # Personal Care
    {"id": "SKU-SOAP75", "name": "Dettol Original Soap 75g", "category": "personal_care", "unit_cost": 42.0},
    {"id": "SKU-PASTE100", "name": "Colgate MaxFresh 100g", "category": "personal_care", "unit_cost": 85.0},
    {"id": "SKU-SHAMPOO180", "name": "Head & Shoulders 180ml", "category": "personal_care", "unit_cost": 190.0},
    # Pharma
    {"id": "SKU-CROCIN", "name": "Crocin Advance 15 tabs", "category": "pharma", "unit_cost": 30.0},
    {"id": "SKU-BANDAID", "name": "Band-Aid Flexible Pack", "category": "pharma", "unit_cost": 65.0},
    {"id": "SKU-ORS", "name": "Electral ORS Sachet", "category": "pharma", "unit_cost": 22.0},
]


def _random_stock(sku_category: str) -> int:
    """Generate realistic random stock quantity based on category."""
    ranges = {
        "dairy": (15, 80),
        "beverages": (20, 120),
        "snacks": (30, 150),
        "food": (10, 60),
        "personal_care": (8, 40),
        "pharma": (5, 30),
    }
    lo, hi = ranges.get(sku_category, (10, 50))
    return random.randint(lo, hi)


async def seed_demo_data(db: AsyncSession):
    """
    Seed demo SKUs and randomized inventory if the database is empty.
    This is idempotent — only runs when no SKUs exist yet.
    """
    # Check if any SKUs already exist
    result = await db.execute(select(func.count(CustomSKU.id)))
    sku_count = result.scalar() or 0

    if sku_count > 0:
        logger.info("Seed: %d SKUs already exist — skipping demo data.", sku_count)
        return

    # ── Seed SKUs ─────────────────────────────────────────────────────────
    logger.info("Seed: Populating %d demo SKUs...", len(DEMO_SKUS))
    for sku_data in DEMO_SKUS:
        db.add(CustomSKU(
            id=sku_data["id"],
            name=sku_data["name"],
            category=sku_data["category"],
            unit_cost=sku_data["unit_cost"],
        ))
    await db.commit()

    # ── Seed inventory for existing hubs ──────────────────────────────────
    hub_result = await db.execute(select(FulfillmentCentre))
    hubs = hub_result.scalars().all()

    if not hubs:
        logger.info("Seed: No hubs configured yet — inventory will be seeded when hubs are added.")
        return

    logger.info("Seed: Generating randomized inventory for %d hubs × %d SKUs...",
                len(hubs), len(DEMO_SKUS))

    for hub in hubs:
        # Each hub gets 60-90% of the catalogue stocked
        stocked_skus = random.sample(DEMO_SKUS, k=random.randint(
            int(len(DEMO_SKUS) * 0.6),
            len(DEMO_SKUS),
        ))
        for sku_data in stocked_skus:
            db.add(HubInventory(
                hub_id=hub.id,
                sku_id=sku_data["id"],
                quantity=_random_stock(sku_data["category"]),
            ))
    await db.commit()
    logger.info("Seed: Demo data seeded successfully.")


async def seed_inventory_for_hub(hub_id: str, db: AsyncSession):
    """
    Seed random inventory for a newly added hub (if demo SKUs exist).
    Called when a new centre is added.
    """
    # Check if demo SKUs exist
    result = await db.execute(select(CustomSKU))
    skus = result.scalars().all()
    if not skus:
        return

    # Check if hub already has inventory
    inv_count = await db.execute(
        select(func.count(HubInventory.id)).where(HubInventory.hub_id == hub_id)
    )
    if (inv_count.scalar() or 0) > 0:
        return

    logger.info("Seed: Auto-populating inventory for new hub %s", hub_id)
    stocked = random.sample(skus, k=random.randint(
        int(len(skus) * 0.6),
        len(skus),
    ))
    for sku in stocked:
        db.add(HubInventory(
            hub_id=hub_id,
            sku_id=sku.id,
            quantity=_random_stock(sku.category),
        ))
    await db.commit()
