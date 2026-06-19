# Earth and Ocean Guardian

Earth and Ocean Guardian is a monolithic Flask web platform for:
- studying endangered animals,
- supporting conservation organizations,
- buying eco-friendly products whose revenue contributes to SDG work,
- and using an on-site AI assistant powered by live platform data.

## Stack
- Frontend: HTML, CSS, JS, Tailwind (CDN)
- Backend: Flask
- ORM: Flask-SQLAlchemy
- Migrations: Flask-Migrate (Alembic)
- Database: SQLite (local) / PostgreSQL (Render)

## Key Features
- High-contrast modern UI with animated reveals and loading experience
- Species Explorer with filter/search
- Organization directory with profiles, announcements, and direct donations
- Ecommerce flow with cart, checkout, order confirmation
- Revenue allocation logic from shop orders to conservation organizations
- AI assistant with persistent chat history per browser session

## Data Models
- Animal
- Organization
- Announcement
- Product
- Donation
- Order
- OrderItem
- ChatMessage

## Main Routes
- `/` Home
- `/animals` Animal explorer
- `/animals/<id>` Animal detail
- `/organizations` Organization listing + announcements
- `/organizations/<slug>` Organization profile + donation form
- `/shop` Product catalog
- `/cart` Cart view
- `/checkout` Checkout form
- `/orders/<id>/confirmation` Order confirmation
- `/assistant` AI chatbot page
- `/api/chat` Chat API endpoint
- `/api/chat/history` Chat history API endpoint

## Run Locally (Windows PowerShell)
1. Create and activate virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
3. Apply database migrations:
   ```powershell
   flask --app app db upgrade
   ```
4. Seed initial data:
   ```powershell
   flask --app app seed
   ```
5. Run the app:
   ```powershell
   flask --app app run --debug
   ```
6. Open: `http://127.0.0.1:5000`

## Migration Workflow
- Generate migration after model changes:
  ```powershell
  flask --app app db migrate -m "describe change"
  ```
- Apply migration:
  ```powershell
  flask --app app db upgrade
  ```

## Seed Commands
- Add missing seed records:
  ```powershell
  flask --app app seed
  ```
- Reset all seeded data:
  ```powershell
  flask --app app seed-reset
  ```

## Deploy to Render (No Manual Platform Config)
This repository now includes [render.yaml](render.yaml), so Render can provision the web service and PostgreSQL database automatically.

1. Push this repository to GitHub.
2. In Render, choose **New +** > **Blueprint**.
3. Select this repository and create the Blueprint.

Render will:
- install dependencies from `requirements.txt`,
- create a managed PostgreSQL database,
- inject `DATABASE_URL` and a generated `FLASK_SECRET_KEY`,
- run migrations + seed data on startup,
- start Gunicorn on the correct Render port.

## Notes
- The chatbot is deterministic and data-aware (it uses platform data rather than a paid external LLM API).
- Local runs use SQLite by default, while Render uses PostgreSQL through `DATABASE_URL`.
