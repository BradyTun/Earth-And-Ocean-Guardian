from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, or_

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "animals.db"


def resolve_database_uri() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        if database_url.startswith("postgres://"):
            # Render can provide a legacy Postgres scheme not accepted by SQLAlchemy.
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return database_url

    return f"sqlite:///{DATABASE_PATH.as_posix()}"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = resolve_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-this-secret-in-production")
app.config["SHOP_CONTRIBUTION_RATE"] = Decimal("0.30")

db = SQLAlchemy(app)
migrate = Migrate(app, db)
_seed_checked = False


class Animal(db.Model):
    __tablename__ = "animals"

    id = db.Column(db.Integer, primary_key=True)
    common_name = db.Column(db.String(120), nullable=False, unique=True)
    scientific_name = db.Column(db.String(180), nullable=False)
    species_group = db.Column(db.String(80), nullable=False)
    conservation_status = db.Column(db.String(80), nullable=False)
    habitat = db.Column(db.String(120), nullable=False)
    region = db.Column(db.String(160), nullable=False)
    threats = db.Column(db.Text, nullable=False)
    how_to_help = db.Column(db.Text, nullable=False)
    population_trend = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.Text, nullable=False)


class Organization(db.Model):
    __tablename__ = "organizations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False, unique=True)
    slug = db.Column(db.String(150), nullable=False, unique=True, index=True)
    about = db.Column(db.Text, nullable=False)
    mission = db.Column(db.Text, nullable=False)
    focus_area = db.Column(db.String(140), nullable=False)
    country = db.Column(db.String(80), nullable=False)
    website_url = db.Column(db.String(255), nullable=False)
    contact_email = db.Column(db.String(180), nullable=False)
    image_url = db.Column(db.Text, nullable=False)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    announcements = db.relationship(
        "Announcement",
        back_populates="organization",
        cascade="all, delete-orphan",
        order_by="desc(Announcement.published_at)",
    )
    donations = db.relationship(
        "Donation",
        back_populates="organization",
        cascade="all, delete-orphan",
    )


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    is_pinned = db.Column(db.Boolean, nullable=False, default=False)
    published_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    organization = db.relationship("Organization", back_populates="announcements")


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False, unique=True)
    slug = db.Column(db.String(150), nullable=False, unique=True, index=True)
    description = db.Column(db.Text, nullable=False)
    impact_note = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(120), nullable=False)
    price_cents = db.Column(db.Integer, nullable=False)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)
    image_url = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class Donation(db.Model):
    __tablename__ = "donations"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    donor_name = db.Column(db.String(120), nullable=False)
    donor_email = db.Column(db.String(180), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), nullable=False, default="confirmed")
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    organization = db.relationship("Organization", back_populates="donations")


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(140), nullable=False)
    customer_email = db.Column(db.String(180), nullable=False)
    customer_phone = db.Column(db.String(40), nullable=True)
    shipping_address = db.Column(db.Text, nullable=False)
    note = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), nullable=False, default="paid")
    total_cents = db.Column(db.Integer, nullable=False)
    contribution_cents = db.Column(db.Integer, nullable=False)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    organization = db.relationship("Organization")
    items = db.relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity = db.Column(db.Integer, nullable=False)
    unit_price_cents = db.Column(db.Integer, nullable=False)
    line_total_cents = db.Column(db.Integer, nullable=False)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product")


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_key = db.Column(db.String(80), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


SAMPLE_ANIMALS: list[dict[str, str]] = [
    {
        "common_name": "Amur Leopard",
        "scientific_name": "Panthera pardus orientalis",
        "species_group": "Mammal",
        "conservation_status": "Critically Endangered",
        "habitat": "Temperate Forest",
        "region": "Russian Far East and Northeast China",
        "threats": "Habitat fragmentation|Poaching|Decline of natural prey",
        "how_to_help": "Support anti-poaching patrols|Choose deforestation-free products|Fund ranger training initiatives",
        "population_trend": "Fewer than 120 adults remain in the wild",
        "image_url": "https://images.unsplash.com/photo-1598755257130-c2aaca1f061c?auto=format&fit=crop&w=1200&q=80",
    },
    {
        "common_name": "Vaquita",
        "scientific_name": "Phocoena sinus",
        "species_group": "Marine Mammal",
        "conservation_status": "Critically Endangered",
        "habitat": "Coastal Marine Waters",
        "region": "Northern Gulf of California, Mexico",
        "threats": "Illegal gillnets|Bycatch in fisheries|Tiny population size",
        "how_to_help": "Promote sustainable seafood choices|Support gillnet-free fishing programs|Advocate for stronger marine enforcement",
        "population_trend": "Estimated fewer than 10 individuals",
        "image_url": "https://images.unsplash.com/photo-1568430462989-44163eb1752f?auto=format&fit=crop&w=1200&q=80",
    },
    {
        "common_name": "Hawksbill Sea Turtle",
        "scientific_name": "Eretmochelys imbricata",
        "species_group": "Reptile",
        "conservation_status": "Critically Endangered",
        "habitat": "Coral Reefs",
        "region": "Tropical Atlantic, Pacific, and Indian Oceans",
        "threats": "Illegal shell trade|Coral reef degradation|Plastic pollution",
        "how_to_help": "Avoid single-use plastics|Support reef restoration programs|Never buy tortoiseshell products",
        "population_trend": "Severe nesting declines across many beaches",
        "image_url": "https://images.unsplash.com/photo-1582967788606-a171c1080cb0?auto=format&fit=crop&w=1200&q=80",
    },
    {
        "common_name": "Sumatran Orangutan",
        "scientific_name": "Pongo abelii",
        "species_group": "Mammal",
        "conservation_status": "Critically Endangered",
        "habitat": "Tropical Rainforest",
        "region": "Sumatra, Indonesia",
        "threats": "Palm oil expansion|Forest fires|Illegal pet trade",
        "how_to_help": "Buy certified sustainable palm oil|Donate to reforestation groups|Support wildlife rescue centers",
        "population_trend": "Population continues to decline in fragmented forests",
        "image_url": "https://images.unsplash.com/photo-1516637090014-cb1ab0d08fc7?auto=format&fit=crop&w=1200&q=80",
    },
    {
        "common_name": "Black Rhino",
        "scientific_name": "Diceros bicornis",
        "species_group": "Mammal",
        "conservation_status": "Critically Endangered",
        "habitat": "Savanna and Shrubland",
        "region": "Eastern and Southern Africa",
        "threats": "Poaching for horn trade|Habitat loss|Political instability",
        "how_to_help": "Back community-led conservation projects|Fund anti-poaching technology|Travel responsibly with eco-certified safaris",
        "population_trend": "Recovering slowly but still highly vulnerable",
        "image_url": "https://images.unsplash.com/photo-1546182990-dffeafbe841d?auto=format&fit=crop&w=1200&q=80",
    },
    {
        "common_name": "Snow Leopard",
        "scientific_name": "Panthera uncia",
        "species_group": "Mammal",
        "conservation_status": "Vulnerable",
        "habitat": "Mountain Ecosystems",
        "region": "Central and South Asia",
        "threats": "Retaliatory killing|Habitat degradation|Climate change",
        "how_to_help": "Support predator-friendly livestock programs|Reduce carbon footprint|Invest in mountain habitat protection",
        "population_trend": "Estimated 4,000 to 6,500 in fragmented ranges",
        "image_url": "https://images.unsplash.com/photo-1530767910492-78b3dbaaf6d1?auto=format&fit=crop&w=1200&q=80",
    },
    {
        "common_name": "Philippine Eagle",
        "scientific_name": "Pithecophaga jefferyi",
        "species_group": "Bird",
        "conservation_status": "Critically Endangered",
        "habitat": "Primary Rainforest",
        "region": "Philippines",
        "threats": "Deforestation|Hunting|Slow reproduction rates",
        "how_to_help": "Protect old-growth forests|Support eagle nest monitoring|Promote forest-friendly livelihoods",
        "population_trend": "Only a few hundred breeding pairs remain",
        "image_url": "https://images.unsplash.com/photo-1591198936750-16d8e15edb9b?auto=format&fit=crop&w=1200&q=80",
    },
    {
        "common_name": "African Penguin",
        "scientific_name": "Spheniscus demersus",
        "species_group": "Bird",
        "conservation_status": "Endangered",
        "habitat": "Rocky Coastlines",
        "region": "Namibia and South Africa",
        "threats": "Overfishing|Oil spills|Rising ocean temperatures",
        "how_to_help": "Support marine protected areas|Donate to seabird rescue groups|Choose responsibly sourced seafood",
        "population_trend": "Population has dropped by over 90 percent in a century",
        "image_url": "https://images.unsplash.com/photo-1551986782-d0169b3f8fa7?auto=format&fit=crop&w=1200&q=80",
    },
]

SAMPLE_ORGANIZATIONS: list[dict[str, Any]] = [
    {
        "name": "Blue Reef Alliance",
        "slug": "blue-reef-alliance",
        "about": "Blue Reef Alliance restores coral ecosystems and protects endangered marine life through science-led coastal programs.",
        "mission": "Advance SDG 14 by rebuilding reef habitats, reducing bycatch, and improving community-led marine stewardship.",
        "focus_area": "SDG 14 - Life Below Water",
        "country": "Indonesia",
        "website_url": "https://www.bluereefalliance.org",
        "contact_email": "team@bluereefalliance.org",
        "image_url": "https://images.unsplash.com/photo-1498623116890-37e912163d5d?auto=format&fit=crop&w=1200&q=80",
        "is_featured": True,
    },
    {
        "name": "Forest Shield Collective",
        "slug": "forest-shield-collective",
        "about": "Forest Shield Collective protects biodiversity corridors where threatened mammals and birds depend on intact rainforest.",
        "mission": "Advance SDG 15 by safeguarding forests, supporting rangers, and restoring native habitat links.",
        "focus_area": "SDG 15 - Life on Land",
        "country": "Brazil",
        "website_url": "https://www.forestshieldcollective.org",
        "contact_email": "hello@forestshieldcollective.org",
        "image_url": "https://images.unsplash.com/photo-1482192505345-5655af888cc4?auto=format&fit=crop&w=1200&q=80",
        "is_featured": True,
    },
    {
        "name": "Wildlife Rescue Network",
        "slug": "wildlife-rescue-network",
        "about": "Wildlife Rescue Network rehabilitates injured animals, trains rapid-response teams, and supports conflict prevention.",
        "mission": "Protect vulnerable species by combining emergency rescue, field medicine, and conservation education.",
        "focus_area": "Species Recovery and Community Action",
        "country": "Kenya",
        "website_url": "https://www.wildliferescuenetwork.org",
        "contact_email": "care@wildliferescuenetwork.org",
        "image_url": "https://images.unsplash.com/photo-1516934024742-b461fba47600?auto=format&fit=crop&w=1200&q=80",
        "is_featured": True,
    },
]

SAMPLE_ANNOUNCEMENTS: list[dict[str, Any]] = [
    {
        "organization_slug": "blue-reef-alliance",
        "title": "Community reef nursery reaches 12,000 coral fragments",
        "body": "Our latest restoration season expanded reef nurseries across three islands and improved fish habitat density by 18 percent.",
        "is_pinned": True,
    },
    {
        "organization_slug": "blue-reef-alliance",
        "title": "Gillnet replacement pilot launched with local fishers",
        "body": "New safer gear pilot reduces bycatch risk for turtles and porpoises while preserving fisher income.",
        "is_pinned": False,
    },
    {
        "organization_slug": "forest-shield-collective",
        "title": "Eight new wildlife camera corridors activated",
        "body": "Monitoring corridors now track jaguars, tapirs, and forest birds to guide anti-fragmentation action.",
        "is_pinned": True,
    },
    {
        "organization_slug": "forest-shield-collective",
        "title": "Community firebreak training completed in 14 villages",
        "body": "Training reduced dry-season fire spread near critical nesting zones and improved emergency coordination.",
        "is_pinned": False,
    },
    {
        "organization_slug": "wildlife-rescue-network",
        "title": "Mobile rescue clinics expanded to northern districts",
        "body": "Field teams now provide faster treatment and relocation support for elephants and large carnivores.",
        "is_pinned": False,
    },
    {
        "organization_slug": "wildlife-rescue-network",
        "title": "Anti-snare patrol equipment fully funded",
        "body": "Donor-backed grants equipped patrol teams with drones, thermal optics, and emergency veterinary kits.",
        "is_pinned": True,
    },
]

SAMPLE_PRODUCTS: list[dict[str, Any]] = [
    {
        "name": "Ocean-Safe Reusable Bottle",
        "slug": "ocean-safe-reusable-bottle",
        "description": "Double-wall stainless steel bottle designed to replace single-use plastics for daily hydration.",
        "impact_note": "Every purchase funds coastal cleanup and marine species monitoring.",
        "category": "Daily Essentials",
        "price_cents": 2800,
        "stock_quantity": 120,
        "image_url": "https://images.unsplash.com/photo-1602143407151-7111542de6e8?auto=format&fit=crop&w=1200&q=80",
        "is_active": True,
    },
    {
        "name": "Bamboo Field Notebook",
        "slug": "bamboo-field-notebook",
        "description": "FSC-certified bamboo fiber notebook for study notes, expedition journals, and planning conservation campaigns.",
        "impact_note": "Revenue supports forest ranger training and habitat corridor mapping.",
        "category": "Stationery",
        "price_cents": 1600,
        "stock_quantity": 240,
        "image_url": "https://images.unsplash.com/photo-1456735190827-d1262f71b8a3?auto=format&fit=crop&w=1200&q=80",
        "is_active": True,
    },
    {
        "name": "Solar Trail Lantern",
        "slug": "solar-trail-lantern",
        "description": "Compact solar-powered lantern with low-energy LED output for camping, patrol work, and emergency use.",
        "impact_note": "A share of profits funds wildlife-safe night patrols in protected areas.",
        "category": "Outdoor Gear",
        "price_cents": 3900,
        "stock_quantity": 80,
        "image_url": "https://images.unsplash.com/photo-1513836279014-a89f7a76ae86?auto=format&fit=crop&w=1200&q=80",
        "is_active": True,
    },
    {
        "name": "Compostable Kitchen Wrap Set",
        "slug": "compostable-kitchen-wrap-set",
        "description": "Plant-based wraps to replace disposable cling film and reduce household waste.",
        "impact_note": "Purchase helps fund urban conservation education programs.",
        "category": "Home",
        "price_cents": 2200,
        "stock_quantity": 130,
        "image_url": "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=1200&q=80",
        "is_active": True,
    },
    {
        "name": "Refillable Eco Cleaning Kit",
        "slug": "refillable-eco-cleaning-kit",
        "description": "Reusable spray bottles and concentrated tablets that reduce plastic waste from cleaning products.",
        "impact_note": "Supports community restoration projects near endangered habitats.",
        "category": "Home",
        "price_cents": 3400,
        "stock_quantity": 95,
        "image_url": "https://images.unsplash.com/photo-1563453392212-326f5e854473?auto=format&fit=crop&w=1200&q=80",
        "is_active": True,
    },
    {
        "name": "Fairtrade Organic Cotton Tote",
        "slug": "fairtrade-organic-cotton-tote",
        "description": "Durable organic cotton tote for shopping and travel, reducing dependence on disposable bags.",
        "impact_note": "Each order contributes directly to species recovery organizations.",
        "category": "Daily Essentials",
        "price_cents": 1800,
        "stock_quantity": 210,
        "image_url": "https://images.unsplash.com/photo-1597484661643-2f5fef640dd3?auto=format&fit=crop&w=1200&q=80",
        "is_active": True,
    },
]


def cents_to_money(cents: int) -> str:
    amount = Decimal(cents) / Decimal("100")
    return f"${amount:,.2f}"


@app.template_filter("money")
def money_filter(cents: int) -> str:
    return cents_to_money(int(cents))


@app.template_filter("human_date")
def human_date_filter(value: datetime) -> str:
    return value.strftime("%d %b %Y")


def parse_amount_to_cents(raw: str) -> int | None:
    try:
        amount = Decimal(raw.strip())
    except (InvalidOperation, AttributeError):
        return None

    if amount <= 0:
        return None

    quantized = (amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(quantized)


def parse_quantity(raw: str | None, *, default: int = 1) -> int:
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default
    return max(value, 0)


def wants_json() -> bool:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.accept_mimetypes
    return accept["application/json"] >= accept["text/html"] and bool(accept["application/json"])


def get_cart() -> dict[int, int]:
    raw_cart = session.get("cart", {})
    if not isinstance(raw_cart, dict):
        return {}

    parsed: dict[int, int] = {}
    for product_id_raw, quantity_raw in raw_cart.items():
        try:
            product_id = int(product_id_raw)
            quantity = int(quantity_raw)
        except (TypeError, ValueError):
            continue

        if quantity > 0:
            parsed[product_id] = quantity

    return parsed


def set_cart(cart: dict[int, int]) -> None:
    session["cart"] = {str(product_id): quantity for product_id, quantity in cart.items() if quantity > 0}
    session.modified = True


def clear_cart() -> None:
    session.pop("cart", None)
    session.modified = True


def cart_snapshot(cart: dict[int, int] | None = None) -> dict[str, Any]:
    local_cart = cart if cart is not None else get_cart()
    if not local_cart:
        return {"items": [], "subtotal_cents": 0}

    product_ids = list(local_cart.keys())
    products = (
        Product.query.filter(Product.id.in_(product_ids), Product.is_active.is_(True))
        .order_by(Product.name.asc())
        .all()
    )
    product_map = {product.id: product for product in products}

    items: list[dict[str, Any]] = []
    subtotal_cents = 0

    for product_id, quantity in local_cart.items():
        product = product_map.get(product_id)
        if product is None:
            continue

        bounded_quantity = min(quantity, product.stock_quantity)
        if bounded_quantity <= 0:
            continue

        line_total = bounded_quantity * product.price_cents
        subtotal_cents += line_total
        items.append(
            {
                "product": product,
                "quantity": bounded_quantity,
                "unit_price_cents": product.price_cents,
                "line_total_cents": line_total,
            }
        )

    return {"items": items, "subtotal_cents": subtotal_cents}


def split_pipe(text: str) -> list[str]:
    return [item.strip() for item in text.split("|") if item.strip()]


def serialize_animal(animal: Animal) -> dict[str, Any]:
    return {
        "id": animal.id,
        "common_name": animal.common_name,
        "scientific_name": animal.scientific_name,
        "species_group": animal.species_group,
        "conservation_status": animal.conservation_status,
        "habitat": animal.habitat,
        "region": animal.region,
        "threats": animal.threats,
        "how_to_help": animal.how_to_help,
        "population_trend": animal.population_trend,
        "image_url": animal.image_url,
        "threats_list": split_pipe(animal.threats),
        "help_list": split_pipe(animal.how_to_help),
    }


def query_animals(
    *,
    search: str = "",
    habitat: str = "",
    status: str = "",
    limit: int | None = None,
    exclude_id: int | None = None,
) -> list[dict[str, Any]]:
    query = Animal.query

    if search:
        like_query = f"%{search}%"
        query = query.filter(
            or_(
                Animal.common_name.ilike(like_query),
                Animal.scientific_name.ilike(like_query),
                Animal.threats.ilike(like_query),
                Animal.region.ilike(like_query),
            )
        )

    if habitat:
        query = query.filter(Animal.habitat == habitat)

    if status:
        query = query.filter(Animal.conservation_status == status)

    if exclude_id is not None:
        query = query.filter(Animal.id != exclude_id)

    query = query.order_by(Animal.common_name.asc())

    if limit is not None:
        query = query.limit(limit)

    return [serialize_animal(animal) for animal in query.all()]


def support_totals_map() -> dict[int, int]:
    totals: dict[int, int] = {}

    donation_rows = (
        db.session.query(Donation.organization_id, func.coalesce(func.sum(Donation.amount_cents), 0))
        .group_by(Donation.organization_id)
        .all()
    )
    for organization_id, total in donation_rows:
        totals[int(organization_id)] = int(total)

    order_rows = (
        db.session.query(Order.organization_id, func.coalesce(func.sum(Order.contribution_cents), 0))
        .filter(Order.organization_id.is_not(None))
        .group_by(Order.organization_id)
        .all()
    )
    for organization_id, total in order_rows:
        totals[int(organization_id)] = totals.get(int(organization_id), 0) + int(total)

    return totals


def get_site_stats() -> dict[str, int]:
    total_animals = db.session.query(func.count(Animal.id)).scalar() or 0
    total_organizations = db.session.query(func.count(Organization.id)).scalar() or 0
    total_products = (
        db.session.query(func.count(Product.id)).filter(Product.is_active.is_(True)).scalar() or 0
    )

    donation_total = db.session.query(func.coalesce(func.sum(Donation.amount_cents), 0)).scalar() or 0
    contribution_total = (
        db.session.query(func.coalesce(func.sum(Order.contribution_cents), 0)).scalar() or 0
    )

    return {
        "total_animals": int(total_animals),
        "total_organizations": int(total_organizations),
        "total_products": int(total_products),
        "total_support_cents": int(donation_total + contribution_total),
    }


def seed_database(force: bool = False) -> int:
    if force:
        ChatMessage.query.delete()
        OrderItem.query.delete()
        Order.query.delete()
        Donation.query.delete()
        Announcement.query.delete()
        Product.query.delete()
        Organization.query.delete()
        Animal.query.delete()
        db.session.commit()

    inserted_total = 0

    if Animal.query.first() is None:
        db.session.add_all([Animal(**animal_data) for animal_data in SAMPLE_ANIMALS])
        inserted_total += len(SAMPLE_ANIMALS)

    if Organization.query.first() is None:
        db.session.add_all([Organization(**organization_data) for organization_data in SAMPLE_ORGANIZATIONS])
        inserted_total += len(SAMPLE_ORGANIZATIONS)
        db.session.flush()

    if Announcement.query.first() is None:
        organizations = {
            organization.slug: organization
            for organization in Organization.query.order_by(Organization.id.asc()).all()
        }
        announcements_to_insert: list[Announcement] = []
        for entry in SAMPLE_ANNOUNCEMENTS:
            organization = organizations.get(entry["organization_slug"])
            if organization is None:
                continue

            announcements_to_insert.append(
                Announcement(
                    organization_id=organization.id,
                    title=entry["title"],
                    body=entry["body"],
                    is_pinned=bool(entry["is_pinned"]),
                )
            )

        db.session.add_all(announcements_to_insert)
        inserted_total += len(announcements_to_insert)

    if Product.query.first() is None:
        db.session.add_all([Product(**product_data) for product_data in SAMPLE_PRODUCTS])
        inserted_total += len(SAMPLE_PRODUCTS)

    db.session.commit()
    return inserted_total


def get_chat_conversation_key() -> str:
    conversation_key = session.get("chat_conversation_key")
    if isinstance(conversation_key, str) and conversation_key:
        return conversation_key

    conversation_key = uuid4().hex
    session["chat_conversation_key"] = conversation_key
    session.modified = True
    return conversation_key


def build_ai_reply(message: str) -> dict[str, Any]:
    cleaned = re.sub(r"\s+", " ", message).strip()
    lowered = cleaned.lower()

    if not cleaned:
        return {
            "reply": "Please share a question about endangered animals, organizations, products, or donations.",
            "suggestions": [
                "Which animals are critically endangered?",
                "Show organizations focused on SDG 14.",
                "What eco products support conservation?",
            ],
        }

    animal_matches = (
        Animal.query.filter(
            or_(
                Animal.common_name.ilike(f"%{cleaned}%"),
                Animal.scientific_name.ilike(f"%{cleaned}%"),
                Animal.habitat.ilike(f"%{cleaned}%"),
                Animal.threats.ilike(f"%{cleaned}%"),
            )
        )
        .order_by(Animal.common_name.asc())
        .limit(3)
        .all()
    )

    organization_matches = (
        Organization.query.filter(
            or_(
                Organization.name.ilike(f"%{cleaned}%"),
                Organization.focus_area.ilike(f"%{cleaned}%"),
                Organization.country.ilike(f"%{cleaned}%"),
                Organization.mission.ilike(f"%{cleaned}%"),
            )
        )
        .order_by(Organization.name.asc())
        .limit(3)
        .all()
    )

    product_matches = (
        Product.query.filter(
            Product.is_active.is_(True),
            or_(
                Product.name.ilike(f"%{cleaned}%"),
                Product.category.ilike(f"%{cleaned}%"),
                Product.description.ilike(f"%{cleaned}%"),
                Product.impact_note.ilike(f"%{cleaned}%"),
            ),
        )
        .order_by(Product.name.asc())
        .limit(3)
        .all()
    )

    sections: list[str] = []
    suggestions: list[str] = []

    if animal_matches:
        lines = [
            f"- {animal.common_name} ({animal.conservation_status}) in {animal.habitat}."
            for animal in animal_matches
        ]
        sections.append("Relevant species found:\n" + "\n".join(lines))
        suggestions.append("Open the Animals page for full threat and habitat details.")

    donation_keywords = ["donate", "donation", "ngo", "organization", "sdg", "support"]
    if organization_matches or any(keyword in lowered for keyword in donation_keywords):
        orgs = organization_matches or Organization.query.order_by(Organization.name.asc()).limit(3).all()
        lines = [f"- {org.name}: {org.focus_area} ({org.country})" for org in orgs]
        sections.append(
            "Partner organizations available for support:\n" + "\n".join(lines)
        )
        suggestions.append("Open Organizations to read announcements and donate.")

    shop_keywords = ["buy", "shop", "product", "eco", "revenue"]
    if product_matches or any(keyword in lowered for keyword in shop_keywords):
        items = product_matches or Product.query.filter(Product.is_active.is_(True)).limit(3).all()
        lines = [
            f"- {item.name}: {cents_to_money(item.price_cents)} ({item.category})"
            for item in items
        ]
        sections.append("Eco products available now:\n" + "\n".join(lines))
        suggestions.append("Visit Shop and checkout to direct revenue to conservation work.")

    if "how can i help" in lowered or "what can i do" in lowered:
        sections.append(
            "Action plan:\n"
            "1. Learn one species profile and its threat factors.\n"
            "2. Donate to one field organization.\n"
            "3. Purchase eco products that allocate revenue to SDG conservation initiatives."
        )

    if not sections:
        sections.append(
            "I can assist with species facts, conservation organizations, and eco product impact. "
            "Ask about a specific animal, SDG focus, or product category."
        )
        suggestions.extend(
            [
                "Which organizations work on SDG 15?",
                "What threatens the Amur Leopard most?",
                "Show eco products for daily use.",
            ]
        )

    return {
        "reply": "\n\n".join(sections),
        "suggestions": suggestions[:4],
    }


@app.context_processor
def inject_layout_state() -> dict[str, Any]:
    cart = get_cart()
    return {"cart_item_count": sum(cart.values())}


@app.route("/")
def home() -> str:
    featured_animals = query_animals(limit=4)
    featured_products = (
        Product.query.filter(Product.is_active.is_(True), Product.stock_quantity > 0)
        .order_by(Product.created_at.desc())
        .limit(4)
        .all()
    )
    featured_organizations = (
        Organization.query.filter(Organization.is_featured.is_(True))
        .order_by(Organization.name.asc())
        .limit(3)
        .all()
    )
    latest_announcements = (
        Announcement.query.order_by(Announcement.is_pinned.desc(), Announcement.published_at.desc())
        .limit(3)
        .all()
    )
    stats = get_site_stats()

    return render_template(
        "index.html",
        featured_animals=featured_animals,
        featured_products=featured_products,
        featured_organizations=featured_organizations,
        latest_announcements=latest_announcements,
        stats=stats,
        active_page="home",
        page_slug="home",
    )


@app.route("/animals")
def animals() -> str:
    search = request.args.get("search", "").strip()
    habitat = request.args.get("habitat", "").strip()
    status = request.args.get("status", "").strip()

    animals_list = query_animals(search=search, habitat=habitat, status=status)

    habitats = [value for (value,) in db.session.query(Animal.habitat).distinct().order_by(Animal.habitat).all()]
    statuses = [
        value
        for (value,) in db.session.query(Animal.conservation_status)
        .distinct()
        .order_by(Animal.conservation_status)
        .all()
    ]

    return render_template(
        "animals.html",
        animals=animals_list,
        habitats=habitats,
        statuses=statuses,
        filters={"search": search, "habitat": habitat, "status": status},
        active_page="animals",
        page_slug="animals",
    )


@app.route("/animals/<int:animal_id>")
def animal_detail(animal_id: int) -> str:
    record = db.session.get(Animal, animal_id)
    if record is None:
        abort(404)

    animal = serialize_animal(record)
    related_animals = query_animals(
        habitat=animal["habitat"],
        exclude_id=animal["id"],
        limit=3,
    )

    return render_template(
        "animal_detail.html",
        animal=animal,
        related_animals=related_animals,
        active_page="animals",
        page_slug="animal-detail",
    )


@app.route("/organizations")
def organizations() -> str:
    organizations_list = Organization.query.order_by(Organization.name.asc()).all()
    latest_announcements = (
        Announcement.query.order_by(Announcement.is_pinned.desc(), Announcement.published_at.desc())
        .limit(12)
        .all()
    )
    totals = support_totals_map()

    return render_template(
        "organizations.html",
        organizations=organizations_list,
        latest_announcements=latest_announcements,
        support_totals=totals,
        active_page="organizations",
        page_slug="organizations",
    )


@app.route("/organizations/<slug>", methods=["GET", "POST"])
def organization_detail(slug: str) -> str:
    organization = Organization.query.filter_by(slug=slug).first_or_404()

    if request.method == "POST":
        donor_name = request.form.get("donor_name", "").strip()
        donor_email = request.form.get("donor_email", "").strip()
        amount_cents = parse_amount_to_cents(request.form.get("amount", ""))
        message = request.form.get("message", "").strip() or None

        validation_errors: list[str] = []
        if len(donor_name) < 2:
            validation_errors.append("Please provide your full name.")
        if "@" not in donor_email:
            validation_errors.append("Please provide a valid email address.")
        if amount_cents is None or amount_cents < 100:
            validation_errors.append("Minimum donation is $1.00.")

        if validation_errors:
            for error_text in validation_errors:
                flash(error_text, "error")
            return redirect(url_for("organization_detail", slug=slug))

        donation = Donation(
            organization_id=organization.id,
            donor_name=donor_name,
            donor_email=donor_email,
            amount_cents=amount_cents,
            message=message,
            status="confirmed",
        )
        db.session.add(donation)
        db.session.commit()

        flash("Donation recorded successfully. Thank you for supporting conservation work.", "success")
        return redirect(url_for("organization_detail", slug=slug))

    recent_donations = (
        Donation.query.filter_by(organization_id=organization.id)
        .order_by(Donation.created_at.desc())
        .limit(8)
        .all()
    )
    announcements = (
        Announcement.query.filter_by(organization_id=organization.id)
        .order_by(Announcement.is_pinned.desc(), Announcement.published_at.desc())
        .all()
    )
    total_raised = support_totals_map().get(organization.id, 0)

    return render_template(
        "organization_detail.html",
        organization=organization,
        announcements=announcements,
        recent_donations=recent_donations,
        total_raised_cents=total_raised,
        active_page="organizations",
        page_slug="organization-detail",
    )


@app.route("/shop")
def shop() -> str:
    category = request.args.get("category", "").strip()
    query = Product.query.filter(Product.is_active.is_(True))

    if category:
        query = query.filter(Product.category == category)

    products = query.order_by(Product.name.asc()).all()
    categories = [
        value
        for (value,) in db.session.query(Product.category)
        .filter(Product.is_active.is_(True))
        .distinct()
        .order_by(Product.category.asc())
        .all()
    ]

    return render_template(
        "shop.html",
        products=products,
        categories=categories,
        selected_category=category,
        active_page="shop",
        page_slug="shop",
    )


@app.route("/shop/<slug>")
def product_detail(slug: str) -> str:
    product = Product.query.filter_by(slug=slug, is_active=True).first_or_404()

    related_products = (
        Product.query.filter(
            Product.is_active.is_(True),
            Product.category == product.category,
            Product.id != product.id,
        )
        .order_by(Product.name.asc())
        .limit(3)
        .all()
    )

    if len(related_products) < 3:
        seen_ids = {product.id, *(item.id for item in related_products)}
        fillers = (
            Product.query.filter(
                Product.is_active.is_(True),
                Product.id.notin_(seen_ids),
            )
            .order_by(Product.created_at.desc())
            .limit(3 - len(related_products))
            .all()
        )
        related_products = related_products + fillers

    contribution_rate: Decimal = app.config["SHOP_CONTRIBUTION_RATE"]
    contribution_cents = int(
        (Decimal(product.price_cents) * contribution_rate).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )

    return render_template(
        "product_detail.html",
        product=product,
        related_products=related_products,
        contribution_cents=contribution_cents,
        active_page="shop",
        page_slug="product-detail",
    )


@app.post("/cart/add/<int:product_id>")
def cart_add(product_id: int):
    product = Product.query.filter_by(id=product_id, is_active=True).first_or_404()
    quantity = parse_quantity(request.form.get("quantity"), default=1)
    quantity = max(quantity, 1)

    cart = get_cart()
    existing_quantity = cart.get(product_id, 0)
    requested_total = existing_quantity + quantity
    cart[product_id] = min(requested_total, product.stock_quantity)
    set_cart(cart)

    message = f"Added {product.name} to cart."

    if wants_json():
        return jsonify(
            {
                "ok": True,
                "message": message,
                "cart_item_count": sum(cart.values()),
                "product_name": product.name,
            }
        )

    flash(message, "success")
    return redirect(request.referrer or url_for("shop"))


@app.post("/cart/update/<int:product_id>")
def cart_update(product_id: int):
    cart = get_cart()
    if product_id not in cart:
        return redirect(url_for("cart_view"))

    quantity = parse_quantity(request.form.get("quantity"), default=1)
    if quantity <= 0:
        cart.pop(product_id, None)
    else:
        product = Product.query.get_or_404(product_id)
        cart[product_id] = min(quantity, product.stock_quantity)

    set_cart(cart)
    flash("Cart updated.", "success")
    return redirect(url_for("cart_view"))


@app.post("/cart/remove/<int:product_id>")
def cart_remove(product_id: int):
    cart = get_cart()
    if product_id in cart:
        cart.pop(product_id)
        set_cart(cart)
        flash("Item removed from cart.", "success")
    return redirect(url_for("cart_view"))


@app.route("/cart")
def cart_view() -> str:
    snapshot = cart_snapshot()
    contribution_rate: Decimal = app.config["SHOP_CONTRIBUTION_RATE"]
    contribution_cents = int(
        (Decimal(snapshot["subtotal_cents"]) * contribution_rate).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )

    return render_template(
        "cart.html",
        cart=snapshot,
        contribution_cents=contribution_cents,
        active_page="shop",
        page_slug="cart",
    )


@app.route("/checkout", methods=["GET", "POST"])
def checkout() -> str:
    snapshot = cart_snapshot()
    items = snapshot["items"]
    subtotal_cents = snapshot["subtotal_cents"]

    if not items:
        flash("Your cart is empty. Add products before checkout.", "error")
        return redirect(url_for("shop"))

    organizations_list = Organization.query.order_by(Organization.name.asc()).all()
    contribution_rate: Decimal = app.config["SHOP_CONTRIBUTION_RATE"]
    contribution_cents = int(
        (Decimal(subtotal_cents) * contribution_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        customer_email = request.form.get("customer_email", "").strip()
        customer_phone = request.form.get("customer_phone", "").strip() or None
        shipping_address = request.form.get("shipping_address", "").strip()
        note = request.form.get("note", "").strip() or None
        organization_id_raw = request.form.get("organization_id", "").strip()

        validation_errors: list[str] = []
        if len(customer_name) < 2:
            validation_errors.append("Please provide your full name.")
        if "@" not in customer_email:
            validation_errors.append("Please provide a valid email address.")
        if len(shipping_address) < 10:
            validation_errors.append("Please provide a complete shipping address.")

        organization_id: int | None = None
        if organization_id_raw:
            try:
                organization_id = int(organization_id_raw)
            except ValueError:
                validation_errors.append("Please choose a valid organization.")

            if organization_id is not None and db.session.get(Organization, organization_id) is None:
                validation_errors.append("Selected organization does not exist.")

        if validation_errors:
            for error_text in validation_errors:
                flash(error_text, "error")
            return redirect(url_for("checkout"))

        order = Order(
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            shipping_address=shipping_address,
            note=note,
            total_cents=subtotal_cents,
            contribution_cents=contribution_cents,
            organization_id=organization_id,
            status="paid",
        )
        db.session.add(order)
        db.session.flush()

        for item in items:
            product: Product = item["product"]
            quantity: int = item["quantity"]

            if product.stock_quantity < quantity:
                db.session.rollback()
                flash(f"Not enough stock for {product.name}. Please update cart.", "error")
                return redirect(url_for("cart_view"))

            product.stock_quantity -= quantity
            order_item = OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=quantity,
                unit_price_cents=item["unit_price_cents"],
                line_total_cents=item["line_total_cents"],
            )
            db.session.add(order_item)

        db.session.commit()
        clear_cart()
        flash("Order placed successfully. Thank you for funding conservation impact.", "success")
        return redirect(url_for("order_confirmation", order_id=order.id))

    return render_template(
        "checkout.html",
        cart=snapshot,
        organizations=organizations_list,
        contribution_rate_percent=int(contribution_rate * 100),
        contribution_cents=contribution_cents,
        active_page="shop",
        page_slug="checkout",
    )


@app.route("/orders/<int:order_id>/confirmation")
def order_confirmation(order_id: int) -> str:
    order = Order.query.get_or_404(order_id)
    return render_template(
        "order_confirmation.html",
        order=order,
        active_page="shop",
        page_slug="order-confirmation",
    )


@app.route("/assistant")
def assistant_page() -> str:
    return render_template(
        "assistant.html",
        active_page="assistant",
        page_slug="assistant",
    )


@app.get("/api/chat/history")
def chat_history_api():
    conversation_key = get_chat_conversation_key()
    messages = (
        ChatMessage.query.filter_by(conversation_key=conversation_key)
        .order_by(ChatMessage.created_at.asc())
        .limit(50)
        .all()
    )
    payload = [
        {
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at.isoformat(),
        }
        for message in messages
    ]
    return jsonify(payload)


@app.post("/api/chat")
def chat_api():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"error": "Message is required."}), 400

    if len(message) > 800:
        return jsonify({"error": "Message is too long. Please keep it under 800 characters."}), 400

    conversation_key = get_chat_conversation_key()

    user_msg = ChatMessage(
        conversation_key=conversation_key,
        role="user",
        content=message,
    )
    db.session.add(user_msg)

    response_data = build_ai_reply(message)
    assistant_msg = ChatMessage(
        conversation_key=conversation_key,
        role="assistant",
        content=response_data["reply"],
    )
    db.session.add(assistant_msg)
    db.session.commit()

    return jsonify(response_data)


@app.route("/help")
def help_redirect():
    return redirect(url_for("organizations"))


@app.errorhandler(404)
def page_not_found(_error: BaseException) -> tuple[str, int]:
    return render_template("404.html", active_page="", page_slug="not-found"), 404


@app.before_request
def ensure_seed_data_for_web() -> None:
    global _seed_checked
    if _seed_checked:
        return

    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    required_tables = {
        "animals",
        "organizations",
        "announcements",
        "products",
        "donations",
        "orders",
        "order_items",
        "chat_messages",
    }
    if required_tables.issubset(table_names):
        seed_database(force=False)
    _seed_checked = True


@app.cli.command("seed")
def seed_command() -> None:
    inspector = inspect(db.engine)
    required_tables = {
        "animals",
        "organizations",
        "announcements",
        "products",
        "donations",
        "orders",
        "order_items",
        "chat_messages",
    }
    if not required_tables.issubset(set(inspector.get_table_names())):
        print("Database schema is incomplete. Run 'flask --app app db upgrade' first.")
        return

    inserted = seed_database(force=False)
    if inserted:
        print(f"Inserted {inserted} seed records.")
    else:
        print("Database already has seed records.")


@app.cli.command("seed-reset")
def seed_reset_command() -> None:
    inspector = inspect(db.engine)
    required_tables = {
        "animals",
        "organizations",
        "announcements",
        "products",
        "donations",
        "orders",
        "order_items",
        "chat_messages",
    }
    if not required_tables.issubset(set(inspector.get_table_names())):
        print("Database schema is incomplete. Run 'flask --app app db upgrade' first.")
        return

    inserted = seed_database(force=True)
    print(f"Re-seeded database with {inserted} records.")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"},
    )
