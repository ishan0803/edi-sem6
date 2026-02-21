# EDI Sem 6 Project

## Overview
This project is a geospatial data visualization and analysis tool built for the EDI Sem 6 curriculum. It consists of a modern, high-performance web application featuring an interactive map interface and a robust backend service.

### Tech Stack
*   **Frontend**: React, Next.js, Deck.gl, MapLibre, TailwindCSS
*   **Backend**: Python, FastAPI, SQLAlchemy
*   **Database**: PostgreSQL with PostGIS extension (for geospatial queries)
*   **Deployment**: Docker & Docker Compose

## Repository Structure
*   `frontend/`: The Next.js React application.
*   `backend/`: The FastAPI Python service.
*   `docker-compose.yml`: To run necessary services.

## Prerequisites
*   Node.js (v18+)
*   Python (3.10+)
*   Docker & Docker Compose (optional, for easy database setup)

## Getting Started

### 1. Database Setup (Optional if using local database)
You can use the provided `docker-compose.yml` to spin up a PostgreSQL instance with PostGIS:
```bash
docker-compose up -d
```

### 2. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Ensure you have the correct `.env` variables set in the root directory.

### 3. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

## Environment Variables
The root directory contains a `.env.example` file. Copy it to `.env` and fill in the required values:
```bash
cp .env.example .env
```
