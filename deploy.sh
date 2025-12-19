set -e

echo "================================================"
echo "  Spike AI Builder - Deployment"
echo "================================================"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "[1/4] Creating virtual environment..."
# Create virtual environment at .venv (as required)
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

echo ""
echo "[2/4] Installing dependencies..."
# Use uv for faster installation if available, otherwise pip
if command -v uv &> /dev/null; then
    echo "Using uv for fast installation..."
    uv pip install -r requirements.txt
else
    echo "Using pip for installation..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

echo ""
echo "[3/4] Checking configuration..."
# Check if .env exists, if not copy from example
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "Creating .env from .env.example..."
        cp .env.example .env
        echo "WARNING: Please update .env with your actual credentials!"
    fi
fi

# Check for credentials.json
if [ ! -f "credentials.json" ]; then
    echo "WARNING: credentials.json not found at project root!"
    echo "GA4 authentication will fail without valid credentials."
fi

echo ""
echo "[4/4] Starting server..."
echo "Server will be available at http://localhost:8080"
echo ""

# Start the server in the background
nohup python -m uvicorn src.api.app:app \
    --host 0.0.0.0 \
    --port 8080 \
    > server.log 2>&1 &

# Store PID for later reference
echo $! > .server.pid

# Wait for server to start
echo "Waiting for server to start..."
for i in {1..30}; do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo ""
        echo "================================================"
        echo "  Server started successfully!"
        echo "  Endpoint: POST http://localhost:8080/query"
        echo "  Health:   GET  http://localhost:8080/health"
        echo "  Logs:     tail -f server.log"
        echo "================================================"
        exit 0
    fi
    sleep 1
    echo -n "."
done

echo ""
echo "ERROR: Server failed to start within 30 seconds"
echo "Check server.log for details"
exit 1
