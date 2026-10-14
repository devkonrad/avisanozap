# AvisanoZap

**Appointment Management & WhatsApp Automation Platform**

AvisanoZap is a Django-based platform designed to simplify appointment management for independent professionals by combining scheduling workflows, asynchronous task processing, and automated WhatsApp communications.

Built as a hands-on engineering project, it explores how Python, relational databases, background workers, and external API integrations can be combined to solve practical business problems in a maintainable, containerized application.

The project is actively developed and deployed, with WhatsApp messaging working in the production environment.

## Key Features

- **Appointment management** — Manage professionals, services, availability, client information, and appointment lifecycles.
- **Professional profiles** — Dedicated professional accounts and public scheduling pages.
- **Automated WhatsApp notifications** — Send appointment confirmations, cancellation notifications, and scheduled reminders.
- **Asynchronous processing** — Use Celery and Redis to handle background tasks outside the main web request cycle.
- **Reliable task execution** — Handle messaging failures and exceptions without unnecessarily interrupting the processing of other notifications.
- **Appointment dashboard** — Browse, filter, paginate, and manage appointments through a server-rendered Django interface.
- **Subscription and billing workflows** — Model subscription plans, payments, and billing states, with an integration path for Asaas checkout.
- **Containerized deployment** — Run the application and its supporting services with Docker Compose.

## Technology Stack

| Area | Technologies |
|---|---|
| Backend | Python, Django |
| Database | PostgreSQL |
| Asynchronous processing | Celery, Redis |
| Messaging integration | Evolution API, WhatsApp via Baileys |
| Billing integration | Asaas |
| Frontend | HTML, Django Templates, server-rendered views |
| Infrastructure | Docker, Docker Compose |
| Data access | Django ORM |
| Application architecture | Modular Django applications, background workers, external service integrations |

## Architecture

AvisanoZap separates core business domains into Django applications, keeping appointment management distinct from billing responsibilities.

```text
                         ┌─────────────────────┐
                         │       Clients       │
                         │    Professionals    │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │     Django Web      │
                         │ Views, Forms, Auth  │
                         └──────┬───────┬──────┘
                                │       │
                    ┌───────────▼─┐   ┌─▼────────────┐
                    │ PostgreSQL  │   │ Celery Tasks │
                    │ Application│   │ Background   │
                    │    Data    │   │ Processing   │
                    └─────────────┘   └──────┬───────┘
                                             │
                                      ┌──────▼──────┐
                                      │    Redis    │
                                      │ Task Broker │
                                      └─────────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │ Evolution API   │
                                    │ WhatsApp        │
                                    └─────────────────┘
```

### Main application domains

- **`appointments`** — Professional profiles, services, availability, appointments, and WhatsApp reminders.
- **`billing`** — Billing plans, subscriptions, payment records, and checkout-related workflows.
- **`core`** — Project configuration, URL routing, and shared application infrastructure.

## Engineering Highlights

### Asynchronous workflows

WhatsApp notifications and scheduled reminders are processed through Celery workers rather than relying exclusively on synchronous HTTP requests.

The implementation includes status tracking, exception handling, and per-message failure handling to help prevent an individual messaging failure from interrupting unrelated work.

### External service integrations

The application integrates with Evolution API to send WhatsApp messages and incorporates Asaas into its billing workflows.

These integrations require handling external service behavior, network failures, asynchronous execution, and application-level state transitions.

### Data modeling and business rules

The application uses PostgreSQL and Django's ORM to represent relationships between professionals, services, appointments, reminders, subscriptions, and payments.

Business rules are enforced through model constraints, validation, query filtering, and transactional operations where appropriate.

### Production-oriented development

AvisanoZap is deployed using Docker-based services, including the Django application, PostgreSQL, Redis, Celery workers, and Evolution API.

Developing and operating the application provides practical experience beyond implementing individual features, including configuration management, database migrations, container orchestration, troubleshooting, and deployment.

## Running Locally

### Prerequisites

- Docker Engine
- Docker Compose
- Environment configuration for the application and its external integrations

### Start the application

Clone the repository and enter the project directory:

```bash
git clone <YOUR_REPOSITORY_URL>
cd avisanozap
```

Configure the required environment variables using the project's settings and deployment configuration.

Build and start the services:

```bash
docker compose up -d --build
```

Apply database migrations:

```bash
docker compose exec web python manage.py migrate
```

Create an administrator account if needed:

```bash
docker compose exec web python manage.py createsuperuser
```

Inspect application logs:

```bash
docker compose logs -f web celery_worker
```

The application depends on correctly configured database, Redis, and messaging services. External integrations may require additional credentials and setup before their features can be used.

## Project Goals

AvisanoZap is both a practical application and a continuous learning project focused on:

- Building maintainable backend applications with Python and Django.
- Designing relational data models and implementing business rules.
- Automating manual workflows through background processing.
- Integrating third-party services through APIs.
- Handling failures and state transitions in asynchronous workflows.
- Deploying and troubleshooting containerized applications.
- Improving software quality, testing practices, and application reliability.

## About

AvisanoZap is an independently developed project created to explore and apply software engineering practices through a real, evolving application.
