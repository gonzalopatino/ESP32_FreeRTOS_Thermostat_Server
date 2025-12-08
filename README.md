# ThermostatRTOS Platform - Backend

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.2-green.svg)](https://djangoproject.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-blue.svg)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-Academic%20Use-red.svg)](#license)

## Overview

The ThermostatRTOS Platform Backend is a Django-based REST API and web dashboard for managing ESP32-based IoT thermostat devices. It provides secure device registration, real-time telemetry ingestion, temperature monitoring with configurable alerts, and comprehensive data management features.

**Author:** Gonzalo Patino  
**Institution:** Southern New Hampshire University  
**Course:** Computer Science Capstone  

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)
- [Security Features](#security-features)
- [License](#license)

---

## Features

### Device Management
- **Device Registration**: Secure registration of ESP32 thermostat devices
- **API Key Management**: SHA-256 hashed API keys with rotation and revocation
- **QR Code Generation**: Easy device provisioning via QR codes

### Telemetry
- **Real-time Ingestion**: High-throughput telemetry endpoint (60 req/min per device)
- **Historical Data**: Query telemetry with flexible time ranges
- **CSV Export**: Export telemetry data for external analysis
- **Storage Quotas**: Per-user storage limits with tiered plans

### Monitoring & Alerts
- **Real-time Charts**: Live temperature monitoring with Chart.js
- **Temperature Alerts**: Configurable high/low threshold email notifications
- **Cooldown Periods**: Prevent alert spam with configurable intervals

### Security
- **Rate Limiting**: Protection against brute-force attacks
- **Content Security Policy (CSP)**: XSS mitigation
- **HTTPS Enforcement**: Secure cookies and HSTS in production
- **Session Management**: HttpOnly cookies with idle timeout

---

## Architecture

```
┌─────────────────┐     HTTPS      ┌──────────────────┐
│  ESP32 Device   │ ─────────────▶ │  Django Backend  │
│  (FreeRTOS)     │   Telemetry    │                  │
└─────────────────┘                │  ┌────────────┐  │
                                   │  │ PostgreSQL │  │
┌─────────────────┐                │  └────────────┘  │
│   Web Browser   │ ◀────────────▶ │                  │
│   (Dashboard)   │   HTML/JSON    │  ┌────────────┐  │
└─────────────────┘                │  │   Redis    │  │
                                   │  │  (Cache)   │  │
                                   └──┴────────────┴──┘
```

---

## Prerequisites

- **Python 3.10+**
- **PostgreSQL 15+**
- **Redis** (optional, for production caching)
- **Git**

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/gonzalopatino/ESP32_FreeRTOS_Thermostat.git
cd ESP32_FreeRTOS_Thermostat/thermostat_platform/backend
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 5. Initialize Database

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Run Development Server

```bash
python manage.py runserver
```

Access the application at: http://127.0.0.1:8000

---

## Configuration

See `.env.example` for all available configuration options.

### Required Settings

| Variable | Description |
|----------|-------------|
| `DJANGO_SECRET_KEY` | Cryptographic key for sessions and signing |
| `POSTGRES_*` | Database connection settings |
| `ALLOWED_HOSTS` | Comma-separated list of valid hostnames |

### Optional Settings

| Variable | Description |
|----------|-------------|
| `REDIS_URL` | Redis connection URL for production caching |
| `EMAIL_*` | SMTP settings for email notifications |
| `ADMIN_EMAIL` | Receive error notifications in production |

---

## API Documentation

### Authentication

#### Device Authentication
Devices authenticate using the `Authorization` header:
```
Authorization: Device <serial_number>:<api_key>
```

#### User Authentication
Users authenticate via session cookies after login.

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/register/` | Register new user |
| `POST` | `/api/auth/login/` | User login |
| `POST` | `/api/auth/logout/` | User logout |
| `POST` | `/api/devices/register/` | Register device |
| `GET` | `/api/devices/` | List user's devices |
| `POST` | `/api/telemetry/ingest/` | Submit telemetry (device auth) |
| `GET` | `/api/telemetry/query/` | Query telemetry data |
| `GET` | `/health/` | Health check |

---

## Project Structure

```
backend/
├── apps/
│   └── api/                    # Main Django application
│       ├── migrations/         # Database migrations
│       ├── static/             # CSS, JavaScript, images
│       ├── templates/          # HTML templates
│       ├── templatetags/       # Custom template tags
│       ├── views/              # View modules
│       │   ├── __init__.py     # Re-exports all views
│       │   ├── api.py          # JSON API endpoints
│       │   ├── auth.py         # Authentication views
│       │   ├── dashboard.py    # HTML dashboard views
│       │   ├── helpers.py      # Shared utilities
│       │   └── telemetry.py    # Telemetry handling
│       ├── admin.py            # Django admin config
│       ├── models.py           # Database models
│       ├── ratelimits.py       # Rate limiting decorators
│       ├── signing.py          # URL signing utilities
│       └── urls.py             # URL routing
├── config/                     # Django project settings
│   ├── settings.py             # Main configuration
│   ├── urls.py                 # Root URL routing
│   ├── wsgi.py                 # WSGI entry point
│   └── asgi.py                 # ASGI entry point
├── docs/                       # Documentation
├── logs/                       # Application logs
├── .env.example                # Environment template
├── .gitignore                  # Git ignore rules
├── manage.py                   # Django CLI
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

---

## Security Features

| Feature | Implementation |
|---------|----------------|
| **Password Policy** | Minimum 10 characters, complexity requirements |
| **Rate Limiting** | Login (5/min), Register (3/hr), Telemetry (60/min) |
| **Session Security** | HttpOnly cookies, 2.5hr idle timeout |
| **HTTPS** | SSL redirect, HSTS, secure cookies (production) |
| **CSP** | Script/style source restrictions |
| **API Key Hashing** | SHA-256, keys shown only once |
| **Timing Attack Prevention** | Constant-time authentication checks |

---

## Development

### Running Tests

```bash
python manage.py test
```

### Code Style

This project follows PEP 8 guidelines. All files include professional headers with author attribution.

### Database Migrations

```bash
# Create new migration after model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate
```

---

## Deployment

### Production Checklist

```bash
python manage.py check --deploy
```

### Environment Variables

Ensure these are set in production:
- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY` (unique, 50+ characters)
- `ALLOWED_HOSTS` (your domain)
- `REDIS_URL` (for caching)
- `EMAIL_*` (for alerts)

---

## License

**Academic Use Only**

This software is developed as part of coursework at Southern New Hampshire University. It may not be copied, distributed, or used for commercial purposes without explicit written permission from the author and the institution.

See the [LICENSE](LICENSE) file for full terms.

---

## Author

**Gonzalo Patino**  
Southern New Hampshire University  
Computer Science Capstone  
2025

---

## Acknowledgments

- Django Project - Web framework
- PostgreSQL - Database
- Chart.js - Real-time visualization
- ESP-IDF & FreeRTOS - Embedded firmware platform
