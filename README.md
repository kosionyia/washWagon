# WashWagon API

WashWagon is a FastAPI backend for a laundry pickup and delivery service.
Customers can reserve capacity-controlled pickup slots, price garments,
pay online or with cash, and follow their orders through live status updates.

The booking system prevents a slot from exceeding its configured capacity,
including when multiple customers attempt to reserve the final space at the
same time.

## Features

### Customers

- Register and log in with a service zone
- View available slots for their zone and date
- Book garments with quantities and receive an upfront price
- Initialize online payments through Paystack
- View their orders and status history
- Receive live order-stage updates through Server-Sent Events (SSE)
- Cancel a booked order before collection and return its space to the slot

### Couriers

- View only their assigned pickups
- Accept unassigned pickups within their zone
- Record cash payments for assigned pickups
- Advance assigned orders through the required delivery stages

### Operations managers

- Create and update zones, slots, capacities, and garment prices
- Create courier accounts and assign couriers to pickups
- View paid revenue grouped by zone
- View the daily courier board

### Payments and live updates

- Paystack transaction initialization
- Signed Paystack webhook verification
- Idempotent processing of duplicate webhook events
- Redis Pub/Sub delivery of order-stage changes to SSE clients

## Order lifecycle

```text
BOOKED → COLLECTED → WASHING → READY → OUT_FOR_DELIVERY → DELIVERED
```

Invalid or out-of-order transitions return HTTP `409 Conflict`. A customer may
cancel an order while it is still `BOOKED`; cancellation releases the reserved
slot capacity.

## Technology stack

- Python 3.14
- FastAPI
- SQLModel and SQLAlchemy
- PostgreSQL
- Alembic
- Redis Pub/Sub
- Paystack
- JWT authentication
- Pytest
- Docker Compose

## Project structure

```text
app/
├── models/         Database tables and relationships
├── repositories/   Reusable database queries
├── routes/         FastAPI HTTP endpoints
├── schemas/        Request and response validation
├── services/       Business logic
└── utils/          Configuration, database, and security helpers

migrations/         Alembic database migrations
scripts/            Seed and manual verification scripts
tests/              Unit, integration, and acceptance tests
```

## Prerequisites

- Python 3.14 or later
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL and Redis, or Docker with Docker Compose

## Environment variables

Create a `.env` file in the project root. Do not commit real credentials.

```env
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5433/washwagon
REDIS_URL=redis://localhost:6379
SQL_ECHO=false

SECRET_KEY=replace-with-a-long-random-value
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_SECONDS=3600

PAYSTACK_SECRET_KEY=your-paystack-test-secret
PAYSTACK_BASE_URL=https://api.paystack.co
PAYSTACK_CALLBACK_URL=http://localhost:3000/payment/callback
PAYSTACK_CURRENCY=NGN

OPS_MANAGER_NAME=WashWagon Ops
OPS_MANAGER_EMAIL=manager@example.com
OPS_MANAGER_PASSWORD=replace-with-a-secure-password

POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
POSTGRES_DB=washwagon
```

The example above is for running the API directly on the host while PostgreSQL
and Redis expose ports through Docker Compose. When the API also runs inside
Docker Compose, use the service names and internal ports instead:

```env
DATABASE_URL=postgresql+psycopg://postgres:password@postgres:5432/washwagon
REDIS_URL=redis://redis:6379
```

The username, password, and database in `DATABASE_URL` must match
`POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`.

## Local setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Start PostgreSQL and Redis

```bash
docker compose up -d postgres redis
```

### 3. Apply database migrations

```bash
uv run alembic upgrade head
```

### 4. Seed reference data and development users

```bash
uv run python -m scripts.seed_data
uv run python -m scripts.seed_users
```

The seed commands are idempotent: running them again does not duplicate the
existing records. Set `SEED_USER_PASSWORD` to override the shared development
user password.

### 5. Start the API

```bash
uv run uvicorn app.main:app --reload
```

The application is then available at `http://localhost:8000`.

## Running the complete stack with Docker

Before starting the application container, use the Docker-specific
`DATABASE_URL` and `REDIS_URL` shown above.

```bash
docker compose build
docker compose up -d postgres redis
docker compose run --rm app uv run alembic upgrade head
docker compose run --rm app uv run python -m scripts.seed_data
docker compose up -d app
```

Alembic migrations must currently be run explicitly; the application
container starts Uvicorn but does not automatically migrate the database.

## API documentation

After starting the API, interactive documentation is available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI schema: `http://localhost:8000/openapi.json`

## Authentication

Register a customer with `POST /auth/register`, then obtain a JWT from
`POST /auth/login`. The login endpoint accepts OAuth2 form data; place the
user's email in the `username` field and the password in the `password` field.

Send the returned token to protected endpoints:

```http
Authorization: Bearer <access-token>
```

The API enforces three roles: `customer`, `courier`, and `ops_manager`.

## Important endpoints

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| `POST` | `/auth/register` | Public | Register a customer |
| `POST` | `/auth/login` | Public | Obtain an access token |
| `POST` | `/users/couriers` | Ops manager | Create a courier account |
| `GET` | `/slots/zone` | Customer | List available slots for a date |
| `POST` | `/slots/` | Ops manager | Create a capacity-controlled slot |
| `POST` | `/orders/` | Customer | Book a pickup and garments |
| `GET` | `/orders/` | Authenticated | List visible orders |
| `POST` | `/orders/{order_id}/accept` | Courier | Accept an unassigned pickup |
| `PATCH` | `/orders/{order_id}/courier` | Ops manager | Assign a courier |
| `PATCH` | `/orders/{order_id}/status` | Authorized actor | Change an order stage |
| `GET` | `/orders/{order_id}/history` | Authorized viewer | Read status history |
| `GET` | `/orders/{order_id}/stream` | Authorized viewer | Receive live SSE updates |
| `POST` | `/payments/orders/{order_id}/initialize` | Customer | Initialize a Paystack payment |
| `GET` | `/payments/orders/{order_id}` | Authorized viewer | Read payment status |
| `POST` | `/payments/orders/{order_id}/cash` | Assigned courier | Record a cash payment |
| `POST` | `/webhooks/payment` | Paystack | Confirm an online payment |
| `GET` | `/reports/revenue` | Ops manager | View paid revenue by zone |
| `GET` | `/reports/courier-board` | Ops manager | View daily courier assignments |

Swagger UI contains the complete request and response schemas.

## Preventing overbooking

Capacity is reserved with an atomic conditional database update. The update
succeeds only when `booked_count < capacity`.

If two customers compete for the final space, one request receives HTTP `201`
and the other receives HTTP `409`. Capacity reservation and order creation
occur in one transaction, so a later booking failure rolls the reservation
back. The acceptance suite sends simultaneous requests to verify this
invariant.

## Payments

Order amounts are stored as integer values in kobo. Initializing an online
payment returns a Paystack authorization URL, but the payment remains pending
until Paystack sends a valid `charge.success` webhook to:

```text
POST /webhooks/payment
```

The API verifies the Paystack HMAC signature and stores processed event IDs so
that provider retries do not apply the same payment twice. In a deployed
environment, configure Paystack with the public HTTPS URL for this endpoint.

## Live order updates

Redis must be available through `REDIS_URL`. An authorized customer, assigned
courier, or operations manager can open:

```text
GET /orders/{order_id}/stream
```

The connection uses `text/event-stream`. Committed order-stage changes are
published through Redis and forwarded to the connected client as SSE events.

## Testing

Run the complete test suite:

```bash
uv run pytest -q
```

Run only the examiner-aligned acceptance tests:

```bash
uv run pytest tests/test_acceptance.py -q
```

`tests/test_acceptance.py` contains one pytest test for every acceptance-
criteria bullet in `questions.txt`, including concurrent last-space booking,
webhook idempotency, invalid stage transitions, and SSE delivery within one
second.

## Authors

Team Wolf Moons

- Majesty
- Kosi
