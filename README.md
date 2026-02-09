# Event Photo Booth Web App

A Flask app for event-specific guest photo capture, admin bulk upload, and a live slideshow display.

## Features
- Admin login and event creation.
- Event-specific guest URLs (ideal for QR codes).
- Mobile-friendly **Take a Picture** upload input (`capture="environment"`).
- Per-event storage under `uploads/<event-slug>/`.
- Admin bulk upload for any event.
- Slideshow page that cycles all event images and auto-refreshes for new uploads.

## Run locally
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open:
- Home: `http://localhost:5000/`
- Admin login: `http://localhost:5000/admin/login`

Default admin password is `admin123` (set `ADMIN_PASSWORD` to override).

## QR code flow
For each event, admin dashboard shows the customer URL (`/e/<event-slug>`). Use that URL in your QR code generator.
