from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib import error as urllib_error, request as urllib_request
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

from seed_data import (
    ALL_ANIMALS,
    LAND_ANIMALS,
    OCEAN_ANIMALS,
    QUIZ_QUESTIONS,
    SAMPLE_ANNOUNCEMENTS,
    SAMPLE_ORGANIZATIONS,
    SAMPLE_PRODUCTS,
)

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "animals.db"


def load_local_env(env_path: Path) -> None:
    """Load KEY=VALUE pairs from a local .env file into os.environ.

    Existing environment variables win, so real deployment secrets are never
    overwritten. This keeps the OpenRouter key out of source control without
    adding a python-dotenv dependency.
    """
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        return


load_local_env(BASE_DIR / ".env")


def resolve_database_uri() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        if database_url.startswith("postgres://"):
            # Render/Vercel can provide a legacy Postgres scheme not accepted by SQLAlchemy.
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        return database_url

    # Serverless platforms such as Vercel expose a read-only filesystem except
    # for /tmp, so keep the fallback SQLite database there. This storage is
    # ephemeral, so set DATABASE_URL to a managed Postgres for durable data.
    if os.getenv("VERCEL"):
        return "sqlite:////tmp/animals.db"

    return f"sqlite:///{DATABASE_PATH.as_posix()}"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = resolve_database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "change-this-secret-in-production")
app.config["SHOP_CONTRIBUTION_RATE"] = Decimal("0.30")
app.config["OPENROUTER_BASE_URL"] = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
app.config["OPENROUTER_API_KEY"] = os.getenv("OPENROUTER_API_KEY", "").strip()
app.config["OPENROUTER_MODEL"] = os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini").strip()

db = SQLAlchemy(app)
migrate = Migrate(app, db)
_seed_checked = False


class Animal(db.Model):
    __tablename__ = "animals"

    id = db.Column(db.Integer, primary_key=True)
    common_name = db.Column(db.String(120), nullable=False, unique=True)
    scientific_name = db.Column(db.String(180), nullable=False)
    species_group = db.Column(db.String(80), nullable=False)
    realm = db.Column(db.String(20), nullable=False, default="Land")
    conservation_status = db.Column(db.String(80), nullable=False)
    habitat = db.Column(db.String(120), nullable=False)
    region = db.Column(db.String(200), nullable=False)
    threats = db.Column(db.Text, nullable=False)
    human_activities = db.Column(db.Text, nullable=False, default="")
    ecological_role = db.Column(db.Text, nullable=False, default="")
    how_to_help = db.Column(db.Text, nullable=False)
    population_trend = db.Column(db.Text, nullable=False)
    fun_fact = db.Column(db.Text, nullable=False, default="")
    why_endangered = db.Column(db.Text, nullable=False, default="")
    emoji = db.Column(db.String(16), nullable=False, default="\U0001F43E")
    accent = db.Column(db.String(20), nullable=False, default="leaf")
    image_url = db.Column(db.Text, nullable=False, default="")


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


def sdg_connection_for(realm: str) -> dict[str, str]:
    if realm == "Ocean":
        return {
            "primary": "SDG 14 - Life Below Water",
            "text": "Keeping this animal safe helps the whole ocean stay healthy and full of life (SDG 14). Learning and sharing its story is part of Quality Education (SDG 4).",
        }
    return {
        "primary": "SDG 15 - Life on Land",
        "text": "Protecting this animal helps forests, grasslands and other land habitats stay healthy (SDG 15). Learning and sharing its story is part of Quality Education (SDG 4).",
    }


def serialize_animal(animal: Animal) -> dict[str, Any]:
    return {
        "id": animal.id,
        "common_name": animal.common_name,
        "scientific_name": animal.scientific_name,
        "species_group": animal.species_group,
        "realm": animal.realm,
        "conservation_status": animal.conservation_status,
        "habitat": animal.habitat,
        "region": animal.region,
        "threats": animal.threats,
        "human_activities": animal.human_activities,
        "ecological_role": animal.ecological_role,
        "how_to_help": animal.how_to_help,
        "population_trend": animal.population_trend,
        "fun_fact": animal.fun_fact,
        "why_endangered": animal.why_endangered,
        "emoji": animal.emoji,
        "accent": animal.accent,
        "image_url": animal.image_url,
        "threats_list": split_pipe(animal.threats),
        "help_list": split_pipe(animal.how_to_help),
        "sdg": sdg_connection_for(animal.realm),
    }


def query_animals(
    *,
    search: str = "",
    realm: str = "",
    habitat: str = "",
    status: str = "",
    limit: int | None = None,
    exclude_id: int | None = None,
) -> list[dict[str, Any]]:
    query = Animal.query

    if realm:
        query = query.filter(Animal.realm == realm)

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
        "total_quiz_questions": len(QUIZ_QUESTIONS),
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
        db.session.add_all([Animal(**animal_data) for animal_data in ALL_ANIMALS])
        inserted_total += len(ALL_ANIMALS)

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


ASSISTANT_SYSTEM_PROMPT = (
    "You are 'Guardian Buddy', a warm and cheerful helper on the 'Earth and Ocean Guardian' "
    "website, which teaches children about endangered land and ocean animals and how to protect them. "
    "Speak simply and kindly, like you are chatting with a curious 8 to 12 year old. "
    "Use short sentences and an encouraging, hopeful tone, and you may use a few friendly emojis (not too many). "
    "You help with endangered animals (land animals connect to SDG 15 - Life on Land, ocean animals connect to "
    "SDG 14 - Life Below Water), why animals are in danger, simple ways kids can help, the animal quiz, the partner "
    "organizations, and the eco-friendly shop. Use the CONTEXT provided (real data from this website) when it is "
    "helpful, and gently point children to the Land Animals, Ocean Animals, or Quiz pages. Keep answers short, "
    "usually under 120 words. Always stay accurate and never share scary or graphic details."
)

KID_SUGGESTIONS = [
    "Which ocean animal is the most endangered?",
    "How can I help save the pandas?",
    "Tell me a fun fact about tigers!",
    "What is SDG 14 and SDG 15?",
]


def build_assistant_context(message: str) -> str:
    """Collect a small block of real site data to ground the AI answer."""
    cleaned = re.sub(r"\s+", " ", message).strip()
    land_count = Animal.query.filter_by(realm="Land").count()
    ocean_count = Animal.query.filter_by(realm="Ocean").count()

    lines: list[str] = [
        f"The website has {land_count} land animals (SDG 15) and {ocean_count} ocean animals (SDG 14), "
        "plus a fun quiz, partner organizations to support, and an eco-friendly shop.",
    ]

    animal_matches: list[Animal] = []
    if cleaned:
        like = f"%{cleaned}%"
        animal_matches = (
            Animal.query.filter(
                or_(
                    Animal.common_name.ilike(like),
                    Animal.scientific_name.ilike(like),
                    Animal.habitat.ilike(like),
                    Animal.species_group.ilike(like),
                    Animal.threats.ilike(like),
                    Animal.region.ilike(like),
                )
            )
            .order_by(Animal.common_name.asc())
            .limit(5)
            .all()
        )

    if animal_matches:
        lines.append("Matching animals:")
        for animal in animal_matches:
            lines.append(
                f"- {animal.common_name} ({animal.realm}, {animal.conservation_status}), "
                f"home: {animal.habitat}. Why in danger: {animal.why_endangered} "
                f"Fun fact: {animal.fun_fact}"
            )

    if cleaned:
        org_matches = (
            Organization.query.filter(
                or_(
                    Organization.name.ilike(f"%{cleaned}%"),
                    Organization.focus_area.ilike(f"%{cleaned}%"),
                    Organization.mission.ilike(f"%{cleaned}%"),
                )
            )
            .order_by(Organization.name.asc())
            .limit(3)
            .all()
        )
        if org_matches:
            lines.append("Matching organizations:")
            for org in org_matches:
                lines.append(f"- {org.name}: {org.focus_area}.")

    return "\n".join(lines)


def call_openrouter(messages: list[dict[str, str]]) -> str | None:
    """Call the OpenRouter chat API. Returns the reply text or None on failure."""
    api_key = app.config.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return None

    url = f"{app.config['OPENROUTER_BASE_URL']}/chat/completions"
    body = json.dumps(
        {
            "model": app.config["OPENROUTER_MODEL"],
            "messages": messages,
            "temperature": 0.6,
            "max_tokens": 500,
        }
    ).encode("utf-8")

    http_request = urllib_request.Request(url, data=body, method="POST")
    http_request.add_header("Content-Type", "application/json")
    http_request.add_header("Authorization", f"Bearer {api_key}")
    http_request.add_header("HTTP-Referer", "https://earth-and-ocean-guardian.vercel.app")
    http_request.add_header("X-Title", "Earth and Ocean Guardian")

    try:
        with urllib_request.urlopen(http_request, timeout=30) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        reply = str(data["choices"][0]["message"]["content"]).strip()
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
        return None

    return reply or None


def generate_ai_reply(message: str, history: list[ChatMessage]) -> dict[str, Any]:
    """Try the live OpenRouter model first, then fall back to the local helper."""
    llm_messages: list[dict[str, str]] = [
        {"role": "system", "content": ASSISTANT_SYSTEM_PROMPT},
        {"role": "system", "content": "CONTEXT (real website data):\n" + build_assistant_context(message)},
    ]
    for item in history[-8:]:
        role = "user" if item.role == "user" else "assistant"
        llm_messages.append({"role": role, "content": item.content})
    llm_messages.append({"role": "user", "content": message})

    reply = call_openrouter(llm_messages)
    if reply:
        return {"reply": reply, "suggestions": KID_SUGGESTIONS[:3]}

    return build_ai_reply(message)


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
    land_count = Animal.query.filter_by(realm="Land").count()
    ocean_count = Animal.query.filter_by(realm="Ocean").count()
    return render_template(
        "animals_hub.html",
        land_count=land_count,
        ocean_count=ocean_count,
        land_preview=query_animals(realm="Land", limit=6),
        ocean_preview=query_animals(realm="Ocean", limit=6),
        active_page="animals",
        page_slug="animals",
    )


def _render_realm_explorer(realm: str, page_slug: str) -> str:
    search = request.args.get("search", "").strip()
    habitat = request.args.get("habitat", "").strip()
    status = request.args.get("status", "").strip()

    animals_list = query_animals(realm=realm, search=search, habitat=habitat, status=status)

    habitats = [
        value
        for (value,) in db.session.query(Animal.habitat)
        .filter(Animal.realm == realm)
        .distinct()
        .order_by(Animal.habitat)
        .all()
    ]
    statuses = [
        value
        for (value,) in db.session.query(Animal.conservation_status)
        .filter(Animal.realm == realm)
        .distinct()
        .order_by(Animal.conservation_status)
        .all()
    ]

    return render_template(
        "animals.html",
        realm=realm,
        animals=animals_list,
        habitats=habitats,
        statuses=statuses,
        filters={"search": search, "habitat": habitat, "status": status},
        active_page="animals",
        page_slug=page_slug,
    )


@app.route("/animals/land")
def animals_land() -> str:
    return _render_realm_explorer("Land", "animals-land")


@app.route("/animals/ocean")
def animals_ocean() -> str:
    return _render_realm_explorer("Ocean", "animals-ocean")


@app.route("/animals/<int:animal_id>")
def animal_detail(animal_id: int) -> str:
    record = db.session.get(Animal, animal_id)
    if record is None:
        abort(404)

    animal = serialize_animal(record)
    related_animals = query_animals(
        realm=animal["realm"],
        habitat=animal["habitat"],
        exclude_id=animal["id"],
        limit=3,
    )
    if len(related_animals) < 3:
        seen_ids = {animal["id"], *(item["id"] for item in related_animals)}
        extra = [
            item
            for item in query_animals(realm=animal["realm"], limit=6)
            if item["id"] not in seen_ids
        ]
        related_animals = (related_animals + extra)[:3]

    return render_template(
        "animal_detail.html",
        animal=animal,
        related_animals=related_animals,
        active_page="animals",
        page_slug="animal-detail",
    )


@app.route("/quiz")
def quiz() -> str:
    return render_template(
        "quiz.html",
        quiz_questions=QUIZ_QUESTIONS,
        active_page="quiz",
        page_slug="quiz",
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
def assistant_page():
    # The AI helper now lives in a floating widget available on every page, so
    # the standalone assistant page simply sends visitors back to the home page.
    return redirect(url_for("home"))


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

    history = (
        ChatMessage.query.filter_by(conversation_key=conversation_key)
        .order_by(ChatMessage.created_at.asc())
        .limit(10)
        .all()
    )

    user_msg = ChatMessage(
        conversation_key=conversation_key,
        role="user",
        content=message,
    )
    db.session.add(user_msg)

    response_data = generate_ai_reply(message, history)
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

    # Serverless hosts such as Vercel never run "flask db upgrade" as a build
    # step, so create any missing tables and seed baseline data on the first
    # request instead. The work is idempotent and is guarded for the lifetime of
    # the warm instance by _seed_checked.
    try:
        db.create_all()
        seed_database(force=False)
    except Exception:
        # A parallel cold start may be performing the same setup; roll back and
        # retry on a later request rather than poisoning this instance.
        db.session.rollback()
        return
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
