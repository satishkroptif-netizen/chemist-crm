# Chemist CRM - B2B Pharma Order Management System

A comprehensive web-based CRM and Order Management System connecting Medical/Medicine Distributors with Retailers (Pharmacies, Chemists, Hospitals, Labs) in India.

## 🏗️ Architecture

- **Backend**: FastAPI (Python 3.11+) with SQLAlchemy 2.0, PostgreSQL, Redis
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS
- **Authentication**: JWT with access/refresh tokens, role-based access control
- **Database Migrations**: Alembic
- **Async Tasks**: Celery with Redis broker

## 📋 Features

### Regulatory & Indian Ecosystem Compliance
- ✅ CDSCO Drug License verification (Form 20, Form 21, Form 20B, Form 21B)
- ✅ GSTIN validation with proper regex patterns
- ✅ FEFO (First-Expired, First-Out) engine with 90-day expiry threshold
- ✅ Batch tracking with Manufacturer Batch Number, Expiry Date, HSN Codes (4-8 digits)
- ✅ E-Way Bill & E-Invoice ready data structures

### Core Retailer Portal
- 🔍 Smart Search: Brand Name, Generic/Molecule Name, Manufacturer, Instrument Specs
- 📦 Bulk & Smart Ordering: Quick-Order matrix, Substitute Finder for out-of-stock items
- 📊 Order & Ledger Transparency: Dispatch status tracking, Financial Ledger, GST Tax Invoices

### Core Distributor Portal
- 💰 Dynamic Pricing & Schemes: 10+1 free, Volume Discounts, Net Rates, Flat Discounts
- 🏭 Multi-Warehouse Logistics: Optimized picking slips grouped by Batch
- 📋 Returns Management: Breakage, Spoilage, Expired Stock with Credit Note workflow

### Technical Architecture
- 🔌 API-First Design: All actions exposed via RESTful APIs
- 🔄 State Machine: Rigid order lifecycle (DRAFT → SUBMITTED → APPROVED_BY_CREDIT → PICKING → INVOICED → DISPATCHED → DELIVERED → CLOSED)
- 🔒 High Availability Inventory: Pessimistic locking during checkout

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 20+ (for local frontend development)
- Python 3.11+ (for local backend development)

### Using Docker (Recommended)

```bash
# Clone the repository
git clone <repository-url>
cd chemist-crm

# Copy environment files
cp backend/.env.example backend/.env

# Start all services
docker-compose up -d

# Run database migrations
docker-compose exec backend alembic upgrade head

# Create super admin user (optional)
docker-compose exec backend python -m app.scripts.create_superuser
```

### Local Development

#### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your settings

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Access Points
- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

## 👥 Default Roles

| Role | Description | Access |
|------|-------------|--------|
| Super Admin | Platform administrator | Full system access |
| Distributor Admin | Distributor management | Distributor portal + user management |
| Distributor Staff | Distributor operations | Distributor portal (read/write) |
| Retailer Admin | Retailer management | Retailer portal + user management |
| Retailer Staff | Retailer operations | Retailer portal (read/write) |

## 📦 Project Structure

```
chemist-crm/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/    # API route handlers
│   │   ├── core/                # Config, security, exceptions
│   │   ├── db/                  # Database session
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # Business logic
│   │   └── main.py              # FastAPI app entry
│   ├── alembic/                 # Database migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/          # Reusable UI components
│   │   ├── contexts/            # React contexts
│   │   ├── hooks/               # Custom hooks
│   │   ├── layouts/             # Page layouts
│   │   ├── pages/               # Page components
│   │   ├── services/            # API service
│   │   ├── types/               # TypeScript types
│   │   └── utils/               # Utility functions
│   ├── package.json
│   └── Dockerfile
└── docker-compose.yml
```

## 🔑 Key API Endpoints

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/change-password` - Change password

### Distributors
- `GET/POST /api/v1/distributors` - List/Create distributors
- `GET/PATCH/DELETE /api/v1/distributors/{id}` - Distributor CRUD

### Retailers
- `GET/POST /api/v1/retailers` - List/Create retailers
- `POST /api/v1/retailers/{id}/verify` - Verify retailer (approve/reject)

### Products
- `GET/POST /api/v1/products` - List/Create products
- `GET /api/v1/products/search?q={query}` - Smart search
- `GET /api/v1/products/{id}/substitutes` - Get substitute products

### Orders
- `GET/POST /api/v1/orders` - List/Create orders
- `POST /api/v1/orders/{id}/submit` - Submit order
- `POST /api/v1/orders/{id}/credit-check` - Credit approval
- `POST /api/v1/orders/{id}/status` - Update order status

### Invoices
- `POST /api/v1/invoices/generate` - Generate invoice from order
- `GET /api/v1/invoices` - List invoices
- `GET /api/v1/invoices/{id}/download` - Download invoice data

### Returns
- `POST /api/v1/returns` - Create return request
- `POST /api/v1/returns/{id}/process` - Approve/Reject return
- `POST /api/v1/returns/{id}/inspect` - Quality inspection
- `POST /api/v1/returns/{id}/receive` - Mark as received

### Dashboard
- `GET /api/v1/dashboard/distributor` - Distributor dashboard stats
- `GET /api/v1/dashboard/retailer` - Retailer dashboard stats
- `GET /api/v1/dashboard/sales-summary` - Sales analytics

## 🧪 Testing

```bash
# Backend tests
cd backend
pytest -v

# Frontend tests
cd frontend
npm run test
```

## 📝 Environment Variables

Key variables in `backend/.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/chemist_crm
SECRET_KEY=your-secret-key-min-32-chars
REDIS_URL=redis://localhost:6379/0
EXPIRY_WARNING_DAYS=90
```

## 🔒 Security Features

- JWT authentication with short-lived access tokens
- Refresh token rotation
- Password hashing with bcrypt
- Role-based access control (RBAC)
- SQL injection prevention via SQLAlchemy ORM
- CORS configuration
- Input validation with Pydantic

## 📄 License

Proprietary - All rights reserved.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 📞 Support

For support, email support@chemist-crm.com or create an issue in the repository.