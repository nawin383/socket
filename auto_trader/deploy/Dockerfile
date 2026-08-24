FROM python:3.11-slim

WORKDIR /app

# Install the repo's own kite_websocket package (used for the live tick feed)
COPY kite_websocket ./kite_websocket
COPY setup.py README.md ./
RUN pip install --no-cache-dir -e .

COPY auto_trader/requirements.txt ./auto_trader/requirements.txt
RUN pip install --no-cache-dir -r auto_trader/requirements.txt

COPY auto_trader ./auto_trader
WORKDIR /app/auto_trader

EXPOSE 8080
CMD ["python", "-m", "src.main"]
