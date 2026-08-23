FROM python:3.12-slim

WORKDIR /app

# Install Microsoft's ODBC Driver 18 runtime as well as build headers for pyodbc.
# unixodbc-dev alone does not provide the configured SQL Server driver.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        unixodbc \
        unixodbc-dev \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
        | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -fsSL "https://packages.microsoft.com/config/debian/$(. /etc/os-release && echo "$VERSION_ID")/prod.list" \
        | sed 's#^deb #deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] #' \
        > /etc/apt/sources.list.d/microsoft-prod.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && odbcinst -q -d -n "ODBC Driver 18 for SQL Server" \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
