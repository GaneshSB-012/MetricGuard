"""
==========================================================
MetricGuard — Log Simulator  (log_simulator.py)
==========================================================

Purpose
-------
Generates realistic application logs that mimic production
software such as Spring Boot, MySQL/PostgreSQL, and Nginx.

The simulator writes structured log lines directly into the
watched log files so the MetricGuard Agent can detect, parse,
and ship them to the backend in real time.

Simulated Services
~~~~~~~~~~~~~~~~~~
1. application.log  — Spring Boot style (REST API, auth, 
                       transactions, cache, scheduled tasks)
2. database.log     — MySQL/PostgreSQL style (connections, 
                       queries, replication, deadlocks)
3. server.log       — Nginx/Apache style (HTTP requests,
                       SSL, rate limiting, upstream errors)

Log Distribution
~~~~~~~~~~~~~~~~
~70% INFO, ~15% WARNING, ~10% ERROR, ~5% CRITICAL
This ensures a realistic mix with enough anomalies for
the ML pipeline to detect.

Usage
-----
    cd MetricGuard
    python devops/agent/log_simulator.py

    # Or with custom interval (seconds between log bursts):
    python devops/agent/log_simulator.py --interval 5

    # Press Ctrl+C to stop
"""

import os
import sys
import time
import random
import argparse
from datetime import datetime


# ==========================================================
# LOG TEMPLATES — Realistic messages per service
# ==========================================================

APPLICATION_LOGS = {
    "INFO": [
        "Application started successfully on port 8080",
        "User authentication successful for user_id={user_id}",
        "REST API request processed: GET /api/v1/users (200 OK) in {latency}ms",
        "REST API request processed: POST /api/v1/orders (201 Created) in {latency}ms",
        "REST API request processed: GET /api/v1/products (200 OK) in {latency}ms",
        "Scheduled task [DataCleanupJob] executed successfully in {latency}ms",
        "Cache hit for key=user_profile_{user_id}, TTL=300s",
        "Cache refreshed for key=product_catalog, {count} entries loaded",
        "Health check endpoint responded with status=UP",
        "Transaction committed: order_id={order_id}, amount=${amount}",
        "Email notification sent to user_id={user_id} for event=ORDER_CONFIRMED",
        "Session created for user_id={user_id}, session_ttl=1800s",
        "Background worker processed {count} messages from queue=notifications",
        "File uploaded successfully: filename=report_{order_id}.pdf, size={size}KB",
        "Configuration reloaded from application.yml",
    ],
    "WARNING": [
        "Slow REST API response: GET /api/v1/reports took {latency}ms (threshold: 2000ms)",
        "Connection pool nearing capacity: {pool_usage}% utilized ({active}/{max} connections)",
        "Retry attempt {retry}/3 for external service call to payment-gateway",
        "Cache miss rate elevated: {cache_miss}% in last 5 minutes",
        "Memory usage high: {memory}% of heap space consumed",
        "Rate limit approaching for client IP {ip}: {count}/100 requests in 60s",
        "Deprecated API endpoint accessed: GET /api/v1/legacy/users",
        "Request payload size exceeds recommended limit: {size}KB (limit: 1024KB)",
        "JWT token expiring soon for user_id={user_id}, remaining TTL=120s",
        "Thread pool saturation warning: {active}/{max} threads active",
    ],
    "ERROR": [
        "NullPointerException in UserService.findById() at line 142",
        "REST API request failed: POST /api/v1/payments (500 Internal Server Error)",
        "Failed to send email notification: SMTP connection refused to mail.example.com:587",
        "Transaction rollback: order_id={order_id}, reason=InsufficientBalanceException",
        "External service timeout: payment-gateway did not respond within 5000ms",
        "File upload failed: IOException - Disk quota exceeded for /uploads/",
        "Authentication failed for user_id={user_id}: InvalidCredentialsException",
        "Circuit breaker OPEN for service=inventory-service after 5 consecutive failures",
        "Unhandled exception in scheduled task [ReportGeneratorJob]: OutOfMemoryError",
        "Failed to deserialize request body: JsonParseException at character position 47",
    ],
    "CRITICAL": [
        "Application health check FAILED — database connection unavailable",
        "Out of memory: Java heap space exceeded 2048MB limit",
        "SSL certificate expires in 24 hours — immediate renewal required",
        "Data integrity violation: duplicate primary key detected in orders table",
        "Deadlock detected in transaction processing pipeline — manual intervention required",
    ],
}

DATABASE_LOGS = {
    "INFO": [
        "Connection established from {ip}:{port} to database=metricguard_db",
        "Query executed successfully: SELECT * FROM metrics WHERE timestamp > NOW() - INTERVAL 1 HOUR ({latency}ms, {count} rows)",
        "Query executed successfully: INSERT INTO anomalies (timestamp, score, cause) VALUES (...) ({latency}ms)",
        "Connection pool initialized: min=5, max=20, idle_timeout=300s",
        "Backup completed: metricguard_db_backup_{date}.sql.gz ({size}MB)",
        "Index rebuilt on table=metrics, column=timestamp ({latency}ms)",
        "Replication lag: 0.2s (within acceptable threshold of 5s)",
        "Slow query log rotated: previous file archived as slow_query_{date}.log",
        "Table statistics updated for metrics ({count} rows analyzed)",
        "Connection closed gracefully from {ip}:{port} (session duration: {latency}s)",
    ],
    "WARNING": [
        "Slow query detected: SELECT * FROM anomalies JOIN metrics ON ... took {latency}ms (threshold: 1000ms)",
        "Connection pool exhaustion warning: {active}/{max} connections in use",
        "Table metrics approaching row limit: {count} rows (threshold: 10M)",
        "Replication lag increased to {latency}s (threshold: 5s)",
        "Disk space for data directory at {disk_usage}% (threshold: 80%)",
        "Lock wait timeout: transaction waiting {latency}s for row lock on anomalies table",
        "Query cache hit ratio degraded to {cache_miss}% (expected >90%)",
        "Temporary table created on disk for complex JOIN query ({size}MB)",
    ],
    "ERROR": [
        "Connection refused from {ip}:{port}: max_connections limit ({max}) reached",
        "Query failed: Deadlock found when trying to get lock on anomalies table",
        "Replication error: binary log position mismatch on replica-02",
        "Failed to write to WAL: disk I/O error on /var/lib/mysql/ib_logfile0",
        "Authentication failure for user=readonly_user from {ip}: Access denied",
        "Corrupt index detected on table=metrics, column=id — repair required",
        "Query timeout: complex aggregation query exceeded 30s limit",
    ],
    "CRITICAL": [
        "Database engine crashed: InnoDB storage engine fatal error",
        "Data directory full: cannot write to /var/lib/mysql/ — 0 bytes free",
        "Primary-replica sync broken: replica-01 disconnected for >60s",
        "Tablespace corruption detected in metrics table — immediate recovery needed",
    ],
}

SERVER_LOGS = {
    "INFO": [
        "HTTP request: {method} /api/v1/{endpoint} from {ip} — {status} ({latency}ms)",
        "TLS handshake completed with {ip} using TLSv1.3 (cipher: AES256-GCM-SHA384)",
        "Upstream server 127.0.0.1:8080 health check passed",
        "Access log rotated: previous file archived as access_{date}.log.gz",
        "Worker process started: pid={pid}, connections=0",
        "Static file served: /assets/css/main.css ({size}KB, cache-hit)",
        "Reverse proxy forwarded request to upstream=app-server-01",
        "Gzip compression applied to response: {endpoint} (ratio: {ratio}%)",
        "Client connection accepted from {ip}:{port}",
        "Keep-alive connection reused for {ip} (request #{count} on this connection)",
    ],
    "WARNING": [
        "Upstream response slow: 127.0.0.1:8080 responded in {latency}ms (threshold: 3000ms)",
        "Client {ip} rate limited: {count} requests in 60s (limit: 100/min)",
        "Request body too large from {ip}: {size}KB (limit: 10240KB)",
        "SSL certificate for *.example.com expires in {days} days",
        "Worker process memory usage high: pid={pid}, RSS={memory}MB (limit: 512MB)",
        "Too many open connections from {ip}: {count}/50 concurrent connections",
        "HTTP/2 stream limit reached for client {ip}: 128 concurrent streams",
    ],
    "ERROR": [
        "Upstream connection failed: 127.0.0.1:8080 — Connection refused",
        "HTTP 502 Bad Gateway: upstream=app-server-01 returned invalid response",
        "HTTP 503 Service Unavailable: all upstream servers are down",
        "SSL handshake failed with {ip}: certificate verification error",
        "Worker process crashed: pid={pid}, signal=SIGSEGV",
        "Failed to bind to port 443: Address already in use",
        "Request timeout: client {ip} did not send full request within 60s",
    ],
    "CRITICAL": [
        "All upstream servers unreachable — service completely unavailable",
        "SSL private key file missing: /etc/ssl/private/server.key not found",
        "Worker process limit reached: cannot spawn new workers (max: 16)",
    ],
}


# ==========================================================
# VALUE GENERATORS
# ==========================================================

def _rand_values():
    """Generate random placeholder values for log templates."""
    return {
        "user_id": random.randint(1000, 9999),
        "order_id": random.randint(10000, 99999),
        "amount": round(random.uniform(9.99, 499.99), 2),
        "latency": random.choice([12, 45, 89, 150, 320, 780, 1200, 2500, 4800, 8500]),
        "count": random.randint(1, 500),
        "size": random.randint(10, 5000),
        "memory": random.randint(60, 98),
        "pool_usage": random.randint(70, 99),
        "active": random.randint(15, 20),
        "max": 20,
        "cache_miss": random.randint(20, 60),
        "disk_usage": random.randint(75, 95),
        "retry": random.randint(1, 3),
        "ip": f"192.168.{random.randint(1,10)}.{random.randint(1,254)}",
        "port": random.randint(30000, 65000),
        "method": random.choice(["GET", "POST", "PUT", "DELETE"]),
        "endpoint": random.choice(["users", "orders", "products", "metrics", "health"]),
        "status": random.choice(["200 OK", "201 Created", "204 No Content", "301 Redirect"]),
        "pid": random.randint(1000, 30000),
        "ratio": random.randint(40, 85),
        "days": random.randint(1, 30),
        "date": datetime.now().strftime("%Y%m%d"),
    }


def _pick_level():
    """Pick a log level based on realistic distribution."""
    roll = random.random()
    if roll < 0.70:
        return "INFO"
    elif roll < 0.85:
        return "WARNING"
    elif roll < 0.95:
        return "ERROR"
    else:
        return "CRITICAL"


def _generate_line(templates: dict) -> str:
    """Generate a single formatted log line."""
    level = _pick_level()
    template = random.choice(templates[level])
    values = _rand_values()

    try:
        message = template.format(**values)
    except (KeyError, IndexError):
        message = template

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"{timestamp} {level} {message}\n"


# ==========================================================
# MAIN SIMULATOR
# ==========================================================

def run_simulator(interval: float = 3.0, watched_dir: str = None):
    """
    Continuously generate and append realistic logs to
    the watched log files.

    Args:
        interval: Seconds between each burst of log lines.
        watched_dir: Path to the watched_logs directory.
    """
    if watched_dir is None:
        # Auto-detect: check common locations
        candidates = [
            os.path.join(os.getcwd(), "watched_logs"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "watched_logs"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "watched_logs"),
        ]
        for c in candidates:
            if os.path.isdir(c):
                watched_dir = c
                break
        if watched_dir is None:
            watched_dir = os.path.join(os.getcwd(), "watched_logs")
            os.makedirs(watched_dir, exist_ok=True)

    log_files = {
        "application": os.path.join(watched_dir, "application.log"),
        "database":    os.path.join(watched_dir, "database.log"),
        "server":      os.path.join(watched_dir, "server.log"),
    }

    templates = {
        "application": APPLICATION_LOGS,
        "database":    DATABASE_LOGS,
        "server":      SERVER_LOGS,
    }

    print("=" * 60)
    print("  MetricGuard — Log Simulator")
    print("=" * 60)
    print(f"  Interval     : {interval}s between bursts")
    print(f"  Watched Dir  : {watched_dir}")
    for name, path in log_files.items():
        print(f"  {name:12s} : {path}")
    print("=" * 60)
    print("  Press Ctrl+C to stop\n")

    cycle = 0

    try:
        while True:
            cycle += 1

            # Each cycle: pick 1-3 random services and write 1-2 lines each
            services = random.sample(list(log_files.keys()), k=random.randint(1, 3))

            for service in services:
                filepath = log_files[service]
                template_set = templates[service]
                num_lines = random.randint(1, 2)

                lines = []
                for _ in range(num_lines):
                    line = _generate_line(template_set)
                    lines.append(line)

                with open(filepath, "a", encoding="utf-8") as f:
                    f.writelines(lines)

                for line in lines:
                    level_color = {
                        "INFO": "\033[92m",      # green
                        "WARNING": "\033[93m",    # yellow
                        "ERROR": "\033[91m",      # red
                        "CRITICAL": "\033[95m",   # magenta
                    }
                    # Extract level from the line
                    parts = line.strip().split(" ", 3)
                    if len(parts) >= 3:
                        lvl = parts[2]
                        color = level_color.get(lvl, "")
                        reset = "\033[0m" if color else ""
                        print(f"  [{service:11s}] {color}{line.strip()}{reset}")

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n{'=' * 60}")
        print(f"  Log Simulator stopped after {cycle} cycles")
        print(f"{'=' * 60}")


# ==========================================================
# Entry point
# ==========================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MetricGuard Log Simulator")
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=3.0,
        help="Seconds between log bursts (default: 3)",
    )
    parser.add_argument(
        "--dir", "-d",
        type=str,
        default=None,
        help="Path to the watched_logs directory",
    )
    args = parser.parse_args()
    run_simulator(interval=args.interval, watched_dir=args.dir)
