import sqlite3
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

TOKEN   = "changeme"          # API Token
DB_PATH = Path("vault.db")    # SQLite DB
HOST    = "0.0.0.0"           # Address
PORT    = 0000                # Port

_local = threading.local()

def get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
    return _local.conn

def has_table(service: str) -> bool:
    cur = get_conn().execute(
        "SELECT count(name) FROM sqlite_master WHERE type='table' AND name=?", (service,)
    )
    return cur.fetchone()[0] == 1

def create_table(service: str) -> None:
    if has_table(service):
        return
    conn = get_conn()
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS `{service}` (
            id   INTEGER NOT NULL UNIQUE,
            kid  TEXT NOT NULL COLLATE NOCASE,
            key_ TEXT NOT NULL COLLATE NOCASE,
            PRIMARY KEY(id AUTOINCREMENT),
            UNIQUE(kid, key_)
        )
    """)
    conn.commit()

def db_get_key(kid: str, service: str) -> Optional[str]:
    for svc in {service, service.lower(), service.upper()}:
        if not has_table(svc):
            continue
        row = get_conn().execute(
            f"SELECT key_ FROM `{svc}` WHERE kid=? AND key_!=?", (kid, "0" * 32)
        ).fetchone()
        if row:
            return row[0]
    return None

def db_get_keys(service: str) -> list[tuple[str, str]]:
    if not has_table(service):
        return []
    rows = get_conn().execute(
        f"SELECT kid, key_ FROM `{service}` WHERE key_!=?", ("0" * 32,)
    ).fetchall()
    return [(r[0], r[1]) for r in rows]

def db_insert_key(service: str, kid: str, key: str) -> bool:
    create_table(service)
    conn = get_conn()
    existing = conn.execute(
        f"SELECT id FROM `{service}` WHERE kid=? AND key_=?", (kid, key)
    ).fetchone()
    if existing:
        return False
    conn.execute(f"INSERT INTO `{service}` (kid, key_) VALUES (?, ?)", (kid, key))
    conn.commit()
    return True

def db_get_services() -> list[str]:
    rows = get_conn().execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
    ).fetchall()
    return [r[0] for r in rows]

def db_key_count(service: str) -> int:
    if not has_table(service):
        return 0
    row = get_conn().execute(f"SELECT count(*) FROM `{service}`").fetchone()
    return row[0]

@asynccontextmanager
async def lifespan(app: FastAPI):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Vault DB : {DB_PATH.resolve()}")
    print(f"  Listening: http://{HOST}:{PORT}/vault/")
    print(f"  Token    : {TOKEN}")
    yield

app = FastAPI(lifespan=lifespan)

def ok(data: Any) -> JSONResponse:
    return JSONResponse({"status_code": 200, "message": data})

def err(msg: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"status_code": code, "error": msg}, status_code=code)


@app.post("/vault/")
async def vault(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return err("Invalid JSON body")

    # auth
    if body.get("token") != TOKEN:
        return err("Unauthorized", 401)

    method = body.get("method", "")
    params = body.get("params", {})

    if method == "GetKey":
        kid = params.get("kid", "").strip().lower()
        service = params.get("service", "").strip()
        if not kid:
            return JSONResponse({"status": "error", "message": "KID is required"}, status_code=400)
        if not service:
            return JSONResponse({"status": "error", "message": "service is required"}, status_code=400)

        key = db_get_key(kid, service)
        if key:
            return ok({"keys": [f"{kid}:{key}"], "session_id": None})
        return ok({"keys": [], "session_id": None})

    elif method == "GetKeys":
        service = params.get("service", "").strip()
        if not service:
            return JSONResponse({"status": "error", "message": "service is required"}, status_code=400)

        pairs = db_get_keys(service)
        keys = [f"{kid}:{key}" for kid, key in pairs]
        return ok({"keys": keys, "count": len(keys), "session_id": None})

    elif method == "InsertKey":
        kid     = params.get("kid", "").strip().lower()
        key     = params.get("key", "").strip().lower()
        service = params.get("service", "").strip()

        if not kid or not key or not service:
            return JSONResponse({"status": "error", "message": "kid:key and service are required"}, status_code=400)
        if len(kid) != 32 or len(key) != 32:
            return JSONResponse({"status": "error", "message": "kid:key must be 32 hex characters"}, status_code=400)
        if key == "0" * 32:
            return JSONResponse({"status": "error", "message": "NULL keys are not allowed"}, status_code=400)

        inserted = db_insert_key(service, kid, key)
        return ok({"inserted": inserted, "status": "inserted" if inserted else "cached", "session_id": None})

    elif method == "GetServices":
        services = db_get_services()
        return ok({"services": services, "session_id": None})

    elif method == "Stats":
        services = db_get_services()
        stats = {svc: db_key_count(svc) for svc in services}
        total = sum(stats.values())
        return ok({"services": stats, "total_keys": total, "session_id": None})

    else:
        return JSONResponse(
            {"status_code": 400, "error": f"Unknown method: {method}", "type": "invalid_method"},
            status_code=400,
        )

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)