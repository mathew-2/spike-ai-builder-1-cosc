# Spike AI Builder

AI-powered backend for answering natural-language questions about **Web Analytics (GA4)** and **SEO Audits (Screaming Frog exports)**.

Built for the Spike AI Builder Hackathon.

---

## Architecture

```
                    +-----------------------------+
                    |    POST /query (port 8080)  |
                    +--------------+--------------+
                                   |
                                   v
                    +-----------------------------+
                    |        Orchestrator         |
                    |   - Intent Detection        |
                    |   - Agent Routing           |
                    |   - Response Aggregation    |
                    +--------------+--------------+
                                   |
              +--------------------+--------------------+
              |                                        |
              v                                        v
   +---------------------+              +---------------------+
   |   Analytics Agent   |              |      SEO Agent      |
   |      (Tier 1)       |              |      (Tier 2)       |
   |                     |              |                     |
   |   Google Analytics  |              |   Google Sheets     |
   |     Data API        |              |  (Screaming Frog)   |
   +---------------------+              +---------------------+
```

---

## Quick Start

### Deploy
```bash
bash deploy.sh
```

### Test
```bash
curl http://localhost:8080/health
```

---

## API Usage

**Endpoint:** `POST http://localhost:8080/query`

### SEO Query
```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Which URLs do not use HTTPS?"}'
```

### GA4 Query
```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{
    "propertyId": "YOUR_GA4_PROPERTY_ID",
    "query": "Show me page views for the last 7 days"
  }'
```

### Multi-Agent Query (Tier 3)
```bash
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{
    "propertyId": "YOUR_GA4_PROPERTY_ID",
    "query": "What are the top 10 pages by views and their title tags?"
  }'
```

---

## Project Structure

```
spike-ai-builder/
├── deploy.sh                # Deployment script (required)
├── credentials.json         # GA4 credentials (replaced by evaluators)
├── .env                     # Environment configuration
├── main.py                  # Application entry point
├── requirements.txt         # Python dependencies
└── src/
    ├── api/
    │   └── app.py           # FastAPI application
    ├── agents/
    │   ├── base.py          # Base agent interface
    │   ├── analytics_agent.py   # GA4 Agent (Tier 1)
    │   └── seo_agent.py     # SEO Agent (Tier 2)
    ├── orchestrator/
    │   └── orchestrator.py  # Multi-agent routing (Tier 3)
    ├── config/
    │   └── settings.py      # Configuration management
    └── utils/
        └── llm_client.py    # LLM client with retry logic
```

---

### Key Capabilities
- Natural language query understanding via LLM
- Live data from GA4 API and Google Sheets
- Automatic intent detection and agent routing
- Exponential backoff for rate limit handling
- Graceful handling of empty/sparse data
- Property-agnostic design (works with any GA4 property)

---

## Configuration

### Environment Variables (.env)
```
LITELLM_API_KEY=sk-your-api-key
LITELLM_BASE_URL=http://3.110.18.218
LITELLM_MODEL=gemini-2.5-flash
GA4_CREDENTIALS_PATH=credentials.json
SEO_SPREADSHEET_ID=1zzf4ax_H2WiTBVrJigGjF2Q3Yz-qy2qMCbAMKvl6VEE
SERVER_PORT=8080
```

### GA4 Credentials
Place your Google Cloud service account JSON at `credentials.json` in the project root.

---

## Sample Test Results

### SEO Query: "Which URLs do not use HTTPS?"
Correctly identified 1 out of 21 URLs using HTTP (http://getspike.ai/about)

### GA4 Query: "Show me page views for the last 7 days"
Successfully queries GA4 API, handles empty data gracefully

### Multi-Agent Query
Routes to both agents, fuses responses correctly

---

## Testing

```bash
# Health check
curl http://localhost:8080/health

# SEO query
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Calculate the percentage of indexable pages"}'

# GA4 query
curl -X POST http://localhost:8080/query \
  -H "Content-Type: application/json" \
  -d '{"propertyId": "YOUR_ID", "query": "Daily breakdown of sessions"}'
```

---

## Assumptions

- GA4 credentials are valid and have Analytics Viewer permissions
- SEO spreadsheet is publicly accessible
- LiteLLM API key has sufficient budget
- All queries are in English

---