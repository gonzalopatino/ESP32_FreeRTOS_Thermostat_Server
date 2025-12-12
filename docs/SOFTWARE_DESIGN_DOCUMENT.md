# Software Design Document

## ThermostatRTOS Platform - Backend Service

---

| Document Information | |
|----------------------|---|
| **Project Name** | ThermostatRTOS Platform |
| **Document Type** | Software Design Document (SDD) |
| **Version** | 1.1 |
| **Author** | Gonzalo Patino |
| **Institution** | Southern New Hampshire University |
| **Date** | December 2025 |
| **Status** | Final |

---

## Table of Contents

1. [Introduction](#1-introduction)
   - 1.1 [Purpose](#11-purpose)
   - 1.2 [Scope](#12-scope)
   - 1.3 [Definitions and Acronyms](#13-definitions-and-acronyms)
   - 1.4 [References](#14-references)
2. [System Overview](#2-system-overview)
   - 2.1 [System Context](#21-system-context)
   - 2.2 [Design Goals](#22-design-goals)
3. [Architecture Design](#3-architecture-design)
   - 3.1 [High-Level Architecture](#31-high-level-architecture)
   - 3.2 [Component Diagram](#32-component-diagram)
   - 3.3 [Technology Stack](#33-technology-stack)
4. [Data Design](#4-data-design)
   - 4.1 [Entity Relationship Diagram](#41-entity-relationship-diagram)
   - 4.2 [Data Models](#42-data-models)
   - 4.3 [Data Flow](#43-data-flow)
5. [Interface Design](#5-interface-design)
   - 5.1 [User Interface](#51-user-interface)
   - 5.2 [API Interface](#52-api-interface)
   - 5.3 [Device Communication Interface](#53-device-communication-interface)
   - 5.4 [Remote Configuration Interface](#54-remote-configuration-interface)
6. [Security Design](#6-security-design)
   - 6.1 [Authentication](#61-authentication)
   - 6.2 [Authorization](#62-authorization)
   - 6.3 [Data Protection](#63-data-protection)
7. [Detailed Design](#7-detailed-design)
   - 7.1 [Module Specifications](#71-module-specifications)
   - 7.2 [Sequence Diagrams](#72-sequence-diagrams)
8. [Quality Attributes](#8-quality-attributes)
9. [Appendices](#9-appendices)

---

## 1. Introduction

### 1.1 Purpose

This Software Design Document (SDD) describes the architectural and detailed design of the ThermostatRTOS Platform Backend. It serves as the primary technical reference for understanding system structure, components, interfaces, and design decisions.

This document is intended for:
- Software developers implementing or maintaining the system
- Academic reviewers evaluating the technical design
- Future maintainers extending the platform

### 1.2 Scope

The ThermostatRTOS Platform Backend provides:
- **Device Management**: Registration and lifecycle management of IoT thermostat devices
- **Telemetry Processing**: Ingestion, storage, and querying of temperature and HVAC data
- **User Dashboard**: Web-based interface for monitoring and configuration
- **Alert System**: Configurable temperature threshold notifications
- **API Services**: RESTful endpoints for device and application integration

**Out of Scope**:
- Embedded device firmware (covered in separate documentation)
- Mobile applications
- Third-party smart home integrations

### 1.3 Definitions and Acronyms

| Term | Definition |
|------|------------|
| **API** | Application Programming Interface |
| **ASGI** | Asynchronous Server Gateway Interface |
| **CSP** | Content Security Policy |
| **CSRF** | Cross-Site Request Forgery |
| **ESP32** | Espressif Systems 32-bit microcontroller |
| **FreeRTOS** | Free Real-Time Operating System |
| **HSTS** | HTTP Strict Transport Security |
| **HVAC** | Heating, Ventilation, and Air Conditioning |
| **IoT** | Internet of Things |
| **JSON** | JavaScript Object Notation |
| **ORM** | Object-Relational Mapping |
| **REST** | Representational State Transfer |
| **SHA-256** | Secure Hash Algorithm 256-bit |
| **WSGI** | Web Server Gateway Interface |
| **XSS** | Cross-Site Scripting |

### 1.4 References

1. Django Documentation - https://docs.djangoproject.com/en/5.2/
2. PostgreSQL Documentation - https://www.postgresql.org/docs/
3. OWASP Security Guidelines - https://owasp.org/
4. ESP-IDF Programming Guide - https://docs.espressif.com/projects/esp-idf/
5. RFC 7519 - JSON Web Token (JWT) - https://tools.ietf.org/html/rfc7519

---

## 2. System Overview

### 2.1 System Context

The ThermostatRTOS Platform operates within an IoT ecosystem connecting smart thermostat devices to cloud services. The backend serves as the central hub for:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         System Context                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌──────────────┐                        ┌──────────────────────┐  │
│   │   ESP32      │                        │   Web Browser        │  │
│   │  Thermostat  │                        │   (User Dashboard)   │  │
│   │   Devices    │                        │                      │  │
│   └──────┬───────┘                        └──────────┬───────────┘  │
│          │                                           │              │
│          │ HTTPS (Device Auth)                       │ HTTPS        │
│          │ Telemetry Data                            │ Session Auth │
│          │                                           │              │
│          ▼                                           ▼              │
│   ┌──────────────────────────────────────────────────────────────┐  │
│   │                                                              │  │
│   │              ThermostatRTOS Backend (Django)                 │  │
│   │                                                              │  │
│   │   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────┐   │  │
│   │   │   API   │  │Dashboard│  │ Alerts  │  │  Rate       │   │  │
│   │   │ Service │  │ Service │  │ Service │  │  Limiter    │   │  │
│   │   └────┬────┘  └────┬────┘  └────┬────┘  └─────────────┘   │  │
│   │        │            │            │                          │  │
│   │        └────────────┼────────────┘                          │  │
│   │                     │                                       │  │
│   │                     ▼                                       │  │
│   │              ┌──────────────┐                               │  │
│   │              │  PostgreSQL  │                               │  │
│   │              │   Database   │                               │  │
│   │              └──────────────┘                               │  │
│   │                                                              │  │
│   └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│   ┌──────────────┐                        ┌──────────────────────┐  │
│   │    SMTP      │◀───────────────────────│   Email Alerts       │  │
│   │   Server     │                        │                      │  │
│   └──────────────┘                        └──────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Design Goals

| Goal | Description | Priority |
|------|-------------|----------|
| **Security** | Protect user data and prevent unauthorized device access | High |
| **Reliability** | Ensure consistent telemetry ingestion without data loss | High |
| **Scalability** | Support growth from single user to multi-tenant deployment | Medium |
| **Maintainability** | Clean code architecture with modular design | High |
| **Performance** | Low-latency API responses for real-time dashboard updates | Medium |
| **Usability** | Intuitive web interface for non-technical users | Medium |

---

## 3. Architecture Design

### 3.1 High-Level Architecture

The system follows a **layered architecture** pattern with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                      PRESENTATION LAYER                          │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  HTML Templates (Bootstrap)  │  JSON API Responses          ││
│  └─────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│                       APPLICATION LAYER                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │   Views     │ │   Forms     │ │ Decorators  │ │  Helpers  │ │
│  │ (auth.py)   │ │             │ │ (rate limit)│ │           │ │
│  │ (api.py)    │ │             │ │             │ │           │ │
│  │ (dashboard) │ │             │ │             │ │           │ │
│  │ (telemetry) │ │             │ │             │ │           │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                        DOMAIN LAYER                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Models: Device, DeviceApiKey, TelemetrySnapshot,           ││
│  │          UserStorageProfile, DeviceAlertSettings            ││
│  └─────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│                     INFRASTRUCTURE LAYER                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ PostgreSQL  │ │   Redis     │ │    SMTP     │ │  Django   │ │
│  │  Database   │ │   Cache     │ │   Mailer    │ │  ORM      │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Django Application                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │   config/        │    │   apps/api/      │    │   External    │  │
│  │                  │    │                  │    │   Services    │  │
│  │  ┌────────────┐  │    │  ┌────────────┐  │    │               │  │
│  │  │ settings.py│  │    │  │ models.py  │  │    │  ┌─────────┐  │  │
│  │  └────────────┘  │    │  └────────────┘  │    │  │ Email   │  │  │
│  │  ┌────────────┐  │    │  ┌────────────┐  │    │  │ Service │  │  │
│  │  │  urls.py   │──┼────┼─▶│  urls.py   │  │    │  └─────────┘  │  │
│  │  └────────────┘  │    │  └────────────┘  │    │               │  │
│  │                  │    │  ┌────────────┐  │    │  ┌─────────┐  │  │
│  └──────────────────┘    │  │   views/   │──┼────┼─▶│PostgreSQL│  │  │
│                          │  │  ├─ api    │  │    │  └─────────┘  │  │
│  ┌──────────────────┐    │  │  ├─ auth   │  │    │               │  │
│  │   Middleware     │    │  │  ├─ dash   │  │    │  ┌─────────┐  │  │
│  │                  │    │  │  ├─ telem  │  │    │  │  Redis  │  │  │
│  │  • Security      │    │  │  └─ helper │  │    │  │ (Cache) │  │  │
│  │  • Session       │    │  └────────────┘  │    │  └─────────┘  │  │
│  │  • CSRF          │    │  ┌────────────┐  │    │               │  │
│  │  • CSP           │    │  │ratelimits  │  │    └───────────────┘  │
│  │  • Rate Limit    │    │  └────────────┘  │                       │
│  │                  │    │  ┌────────────┐  │                       │
│  └──────────────────┘    │  │ signing.py │  │                       │
│                          │  └────────────┘  │                       │
│                          │                  │                       │
│                          └──────────────────┘                       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.3 Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Web Framework** | Django 5.2 | Mature, batteries-included, excellent ORM |
| **Database** | PostgreSQL 15+ | ACID compliance, JSON support, reliability |
| **Cache** | Redis / LocMemCache | Rate limiting, session caching |
| **Rate Limiting** | django-ratelimit | Configurable, decorator-based |
| **Security** | django-csp | Content Security Policy headers |
| **Frontend** | Bootstrap 5 | Responsive, professional UI |
| **Charts** | Chart.js | Real-time data visualization |
| **WSGI Server** | Gunicorn (production) | Multi-worker process model |

---

## 4. Data Design

### 4.1 Entity Relationship Diagram

```
┌─────────────────────┐       ┌─────────────────────┐
│       User          │       │  UserStorageProfile │
│ (Django Auth)       │       │                     │
├─────────────────────┤       ├─────────────────────┤
│ id (PK)             │──1:1─▶│ id (PK)             │
│ username            │       │ user_id (FK)        │
│ email               │       │ plan                │
│ password (hashed)   │       │ cached_usage_bytes  │
└─────────┬───────────┘       │ usage_last_calc     │
          │                   └─────────────────────┘
          │ 1:N
          ▼
┌─────────────────────┐       ┌─────────────────────┐
│      Device         │       │  DeviceAlertSettings│
├─────────────────────┤       ├─────────────────────┤
│ id (PK)             │──1:1─▶│ id (PK)             │
│ serial_number (UQ)  │       │ device_id (FK)      │
│ owner_id (FK→User)  │       │ alerts_enabled      │
│ name                │       │ high_temp_threshold │
│ created_at          │       │ low_temp_threshold  │
│ last_seen           │       │ cooldown_minutes    │
└─────────┬───────────┘       └─────────────────────┘
          │
          │ 1:N
          ▼
┌─────────────────────┐       ┌─────────────────────┐
│   DeviceApiKey      │       │  TelemetrySnapshot  │
├─────────────────────┤       ├─────────────────────┤
│ id (PK)             │       │ id (PK)             │
│ device_id (FK)      │       │ device_id (indexed) │
│ key_hash (SHA-256)  │       │ mode                │
│ created_at          │       │ setpoint_c          │
│ expires_at          │       │ temp_inside_c       │
│ is_active           │       │ temp_outside_c      │
└─────────────────────┘       │ humidity_percent    │
                              │ hysteresis_c        │
                              │ output              │
                              │ device_ts           │
                              │ server_ts           │
                              └─────────────────────┘
```

### 4.2 Data Models

#### Device Model
```python
class Device(models.Model):
    serial_number = models.CharField(max_length=64, unique=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)  # Auto-detected from telemetry
```

#### TelemetrySnapshot Model
```python
class TelemetrySnapshot(models.Model):
    device_id = models.CharField(max_length=64, db_index=True)
    mode = models.CharField(max_length=16)  # AUTO, HEAT, COOL, OFF
    setpoint_c = models.FloatField()
    temp_inside_c = models.FloatField()
    temp_outside_c = models.FloatField(null=True)
    humidity_percent = models.FloatField(null=True)
    hysteresis_c = models.FloatField(default=0.5)
    output = models.CharField(max_length=16)  # HEAT_ON, COOL_ON, OFF
    device_ts = models.DateTimeField()
    server_ts = models.DateTimeField(auto_now_add=True)
```

### 4.3 Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Telemetry Ingestion Flow                        │
└─────────────────────────────────────────────────────────────────────┘

  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │  ESP32   │    │   Rate   │    │  Auth    │    │  Quota   │
  │  Device  │───▶│  Limiter │───▶│  Check   │───▶│  Check   │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘
       │                                               │
       │ POST /api/telemetry/ingest/                   │
       │ Authorization: Device SN:KEY                  ▼
       │                                         ┌──────────┐
       │                                         │  Parse   │
       │                                         │  JSON    │
       │                                         └────┬─────┘
       │                                              │
       ▼                                              ▼
  ┌──────────┐                                  ┌──────────┐
  │ Response │◀─────────────────────────────────│  Store   │
  │  200 OK  │                                  │   DB     │
  └──────────┘                                  └────┬─────┘
                                                     │
                                                     ▼
                                               ┌──────────┐
                                               │  Check   │
                                               │  Alerts  │
                                               └────┬─────┘
                                                    │
                                                    ▼
                                               ┌──────────┐
                                               │  Send    │
                                               │  Email   │
                                               └──────────┘
```

---

## 5. Interface Design

### 5.1 User Interface

The web dashboard follows a clean, responsive design:

```
┌─────────────────────────────────────────────────────────────────────┐
│  ThermostatRTOS                                    [User ▼] [Logout]│
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐  ┌────────────────────────────────────────────┐   │
│  │  Navigation  │  │                 Content Area               │   │
│  │              │  │                                            │   │
│  │  • Devices   │  │  ┌────────────────────────────────────┐    │   │
│  │  • Settings  │  │  │        Real-time Chart             │    │   │
│  │  • Data Mgmt │  │  │                                    │    │   │
│  │              │  │  └────────────────────────────────────┘    │   │
│  │              │  │                                            │   │
│  │              │  │  ┌────────────────────────────────────┐    │   │
│  │              │  │  │      Recent Telemetry Table        │    │   │
│  │              │  │  │                                    │    │   │
│  │              │  │  └────────────────────────────────────┘    │   │
│  │              │  │                                            │   │
│  └──────────────┘  └────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 API Interface

#### Request/Response Format

All API endpoints use JSON:

**Request:**
```json
POST /api/telemetry/ingest/
Content-Type: application/json
Authorization: Device ESP32-001:abc123...

{
    "mode": "AUTO",
    "setpoint_c": 22.0,
    "temp_inside_c": 21.5,
    "temp_outside_c": 5.0,
    "humidity_percent": 45.0,
    "hysteresis_c": 0.5,
    "output": "HEAT_ON",
    "device_ip": "192.168.1.100",
    "timestamp": "2025-12-08T10:30:00Z"
}
```

**Response:**
```json
{
    "status": "ok",
    "id": 12345
}
```

### 5.3 Device Communication Interface

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Device Authentication Flow                        │
└─────────────────────────────────────────────────────────────────────┘

   Device                                              Backend
     │                                                    │
     │  1. Registration (via Dashboard QR Code)           │
     │  ─────────────────────────────────────────────▶   │
     │                                                    │
     │  2. Receive API Key (shown once)                   │
     │  ◀─────────────────────────────────────────────   │
     │                                                    │
     │  3. Store key securely in NVS                      │
     │  ────────────────────────────────────────         │
     │                                                    │
     │  4. POST /api/telemetry/ingest/                    │
     │     Authorization: Device SN:KEY                   │
     │     Body includes: device_ip for auto-detection    │
     │  ─────────────────────────────────────────────▶   │
     │                                                    │
     │  5. Backend stores IP, hashes key, validates       │
     │  ◀─────────────────────────────────────────────   │
     │     200 OK / 403 Forbidden                         │
     │                                                    │
```

### 5.4 Remote Configuration Interface

The dashboard communicates directly with ESP32 devices over the local network for real-time configuration changes.

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Remote Configuration Flow                           │
└─────────────────────────────────────────────────────────────────────┘

   Dashboard                    ESP32 Device
     │                              │
     │  1. User selects device      │
     │     (IP auto-detected from   │
     │      telemetry or manual)    │
     │                              │
     │  2. GET /api/config          │
     │  ───────────────────────────▶│
     │                              │
     │  3. Current config response  │
     │  ◀───────────────────────────│
     │     {setpoint, hysteresis,   │
     │      mode}                   │
     │                              │
     │  4. User adjusts values      │
     │                              │
     │  5. POST /api/config         │
     │     {setpoint_c: 23.5,       │
     │      hysteresis_c: 0.8,      │
     │      mode: "AUTO"}           │
     │  ───────────────────────────▶│
     │                              │
     │  6. Device applies config    │
     │     (NVS persistence)        │
     │  ◀───────────────────────────│
     │     {status: "ok", ...}      │
     │                              │
```

#### ESP32 Local API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/config` | Retrieve current thermostat configuration |
| `POST` | `/api/config` | Update setpoint, hysteresis, and/or mode |
| `OPTIONS` | `/api/config` | CORS preflight support |

#### Configuration Parameters

| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `setpoint_c` | float | 15.0 - 28.0 | Target temperature in Celsius |
| `hysteresis_c` | float | 0.1 - 2.0 | Deadband width in Celsius |
| `mode` | string | OFF, HEAT, COOL, AUTO | Operating mode |

---

## 6. Security Design

### 6.1 Authentication

| Component | Mechanism |
|-----------|-----------|
| **User Authentication** | Session-based with Django's authentication system |
| **Device Authentication** | Custom header: `Authorization: Device serial:key` |
| **API Key Storage** | SHA-256 hash only (plaintext never stored) |
| **Password Storage** | PBKDF2 with SHA-256 (Django default) |

### 6.2 Authorization

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Authorization Matrix                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Resource              Anonymous   Authenticated   Device   Admin   │
│  ─────────────────────────────────────────────────────────────────  │
│  /health/              ✓           ✓               ✓        ✓       │
│  /accounts/login/      ✓           ✓               ✗        ✓       │
│  /dashboard/*          ✗           ✓               ✗        ✓       │
│  /api/devices/         ✗           ✓ (own only)    ✗        ✓       │
│  /api/telemetry/query/ ✗           ✓ (own only)    ✗        ✓       │
│  /api/telemetry/ingest/✗           ✗               ✓        ✗       │
│  /admin/               ✗           ✗               ✗        ✓       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.3 Data Protection

| Threat | Mitigation |
|--------|------------|
| **SQL Injection** | Django ORM with parameterized queries |
| **XSS** | Content Security Policy, template auto-escaping |
| **CSRF** | Django CSRF middleware, SameSite cookies |
| **Brute Force** | Rate limiting on auth endpoints |
| **Session Hijacking** | HttpOnly cookies, secure flag, idle timeout |
| **Man-in-the-Middle** | HTTPS enforcement, HSTS |
| **Timing Attacks** | Constant-time hash comparison |

---

## 7. Detailed Design

### 7.1 Module Specifications

#### views/telemetry.py

| Function | Description | Auth Required |
|----------|-------------|---------------|
| `ingest_telemetry` | Receive and store device telemetry | Device API Key |
| `telemetry_query` | Query telemetry with time range filters | User Session |
| `realtime_query` | Fetch recent data for real-time charts | User Session |
| `export_telemetry_csv` | Export telemetry to CSV format | User Session |

#### views/auth.py

| Function | Description | Auth Required |
|----------|-------------|---------------|
| `register_page` | HTML registration form | None |
| `register_user` | JSON user registration | None |
| `login_user` | JSON user login | None |
| `logout_user` | JSON user logout | User Session |
| `settings_page` | User settings page | User Session |

### 7.2 Sequence Diagrams

#### User Login Flow

```
Browser          Django           Database         Cache
   │                │                 │               │
   │ POST /login    │                 │               │
   │───────────────▶│                 │               │
   │                │                 │               │
   │                │ Check rate limit│               │
   │                │─────────────────┼──────────────▶│
   │                │                 │               │
   │                │ Query user      │               │
   │                │────────────────▶│               │
   │                │                 │               │
   │                │ Verify password │               │
   │                │◀────────────────│               │
   │                │                 │               │
   │                │ Create session  │               │
   │                │────────────────▶│               │
   │                │                 │               │
   │ Set-Cookie     │                 │               │
   │◀───────────────│                 │               │
   │                │                 │               │
```

---

## 8. Quality Attributes

| Attribute | Requirement | Implementation |
|-----------|-------------|----------------|
| **Performance** | API response < 200ms | Database indexing, query optimization |
| **Availability** | 99.9% uptime | Health checks, graceful degradation |
| **Scalability** | 1000+ concurrent devices | Connection pooling, async capable |
| **Security** | OWASP Top 10 compliance | CSP, rate limiting, input validation |
| **Maintainability** | Modular codebase | Separated views, documented code |
| **Testability** | Unit test coverage | Django TestCase framework |

---

## 9. Appendices

### A. Configuration Reference

See `.env.example` for complete configuration options.

### B. API Endpoint Reference

See `README.md` for API documentation.

### C. Database Migrations

Migrations are managed via Django:
```bash
python manage.py makemigrations
python manage.py migrate
```

### D. Deployment Checklist

```bash
python manage.py check --deploy
```

---

**Document Control**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Dec 2025 | Gonzalo Patino | Initial release |
| 1.1 | Dec 2025 | Gonzalo Patino | Added Remote Configuration Interface (5.4), ESP32 Local API, device_ip telemetry field |

---

*This document is part of the ThermostatRTOS Platform project developed for Southern New Hampshire University.*
