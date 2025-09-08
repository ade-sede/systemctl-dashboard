# Agent Guidelines for Systemctl Dashboard

## Build/Test Commands
- **Run application**: `./dashboard.py --port 8080 --config-dir ~/.config/systemctl-dashboard --base-url /health/`
- **Development**: Use devbox shell for Python 3.11 environment

## Code Style Guidelines
- **Language**: Python 3.11+ with standard library only
- **Imports**: Group standard library imports at top, maintain alphabetical order
- **Formatting**: 4-space indentation, snake_case naming, max line length ~100 chars
- **Classes**: PascalCase class names, descriptive method names
- **Error handling**: Use try/except blocks with specific exceptions, return error dicts for API responses
- **Database**: SQLite with context managers, parameterized queries to prevent injection
- **HTTP**: Simple BaseHTTPRequestHandler with JSON responses, CORS headers included
- **Logging**: Minimal logging, use subprocess.run() with timeout for system commands
- **File structure**: Single-file application with HTML template in templates/
- **Constants**: Use uppercase for timeouts (5s for status, 10s for control operations)

## Architecture
- Single Python file with embedded HTTP server
- SQLite database for service tracking and UI state
- HTML template with inline CSS/JavaScript
- REST API endpoints under /api/ prefix
