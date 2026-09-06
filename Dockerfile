FROM python:3.12-slim

WORKDIR /app

# Dependencies first so this layer is cached unless requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Default command runs the dashboard/API under waitress (a real
# production WSGI server - unlike Flask's dev server, it actually
# handles concurrent requests). The collector service overrides
# this with `python collector.py` - see docker-compose.yml.
CMD ["waitress-serve", "--host=0.0.0.0", "--port=5000", "--threads=8", "app:app"]
