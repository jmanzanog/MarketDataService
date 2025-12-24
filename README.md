# Market Data Service

A lightweight Python microservice that provides stock market data via REST API, powered by [yfinance](https://github.com/ranaroussi/yfinance).

## Features

- 🔍 **ISIN Search**: Search for financial instruments by ISIN code
- 💰 **Real-time Quotes**: Get current stock prices for any symbol
- 🌐 **Global Coverage**: Supports US, UK, EU, Asian markets
- 🚀 **Fast**: Built with FastAPI for high performance
- 🐳 **Docker Ready**: Production-ready containerization

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/v1/search/{isin}` | Search instrument by ISIN |
| `GET` | `/api/v1/quote/{symbol}` | Get current quote for symbol |
| `GET` | `/docs` | OpenAPI documentation |

### Examples

**Search by ISIN:**
```bash
curl http://localhost:8000/api/v1/search/US0378331005
```

Response:
```json
{
  "isin": "US0378331005",
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "type": "stock",
  "currency": "USD",
  "exchange": "NASDAQ"
}
```

**Get Quote:**
```bash
curl http://localhost:8000/api/v1/quote/AAPL
```

Response:
```json
{
  "symbol": "AAPL",
  "price": "195.5000",
  "currency": "USD",
  "time": "2024-12-24T15:00:00+00:00"
}
```

## Quick Start

### Docker (Recommended)

```bash
docker compose up --build
```

The service will be available at `http://localhost:8000`

### Local Development

1. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the service:
```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## Configuration

Environment variables (see `.env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Service port | `8000` |
| `HOST` | Service host | `0.0.0.0` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DEBUG` | Enable debug mode | `false` |

## Testing

Run unit tests:
```bash
pytest tests/ -v
```

Run integration tests (requires internet):
```bash
pytest tests/ -v -m integration
```

## Kubernetes Deployment

Example K8s deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: market-data-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: market-data-service
  template:
    metadata:
      labels:
        app: market-data-service
    spec:
      containers:
      - name: market-data-service
        image: ghcr.io/your-username/market-data-service:latest
        ports:
        - containerPort: 8000
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        resources:
          limits:
            memory: "256Mi"
            cpu: "500m"
          requests:
            memory: "128Mi"
            cpu: "100m"
---
apiVersion: v1
kind: Service
metadata:
  name: market-data-service
spec:
  selector:
    app: market-data-service
  ports:
  - port: 8000
    targetPort: 8000
  type: ClusterIP
```

## Integration with StockTracker

To use this service with your Go StockTracker application:

1. Deploy this service to your K3s cluster
2. Configure the StockTracker to use this as the market data provider
3. The Go client will call:
   - `GET /api/v1/search/{isin}` for `SearchByISIN`
   - `GET /api/v1/quote/{symbol}` for `GetQuote`

## License

MIT