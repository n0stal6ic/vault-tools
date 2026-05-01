import sys
import requests
session = requests.Session()
session.headers.update({"User-Agent": "unshackle v4.0.0"})
api_session_id = None

def insert_key(host: str, token: str, kid: str, key: str, service: str) -> bool:
    global api_session_id
    params = {"kid": kid, "key": key, "service": service.lower()}
    if api_session_id:
        params["session_id"] = api_session_id
    r = session.post(host, json={"method": "InsertKey", "params": params, "token": token})
    res = r.json()
    if isinstance(res.get("message"), dict):
        if sid := res["message"].get("session_id"):
            api_session_id = sid
        return res["message"].get("inserted", False)
    return False

def parse_pairs(text: str) -> list[tuple[str, str]]:
    pairs = []
    for line in text.replace(";", "\n").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        kid, key = line.split(":", 1)
        kid, key = kid.strip().lower(), key.strip().lower()
        if len(kid) == 32 and len(key) == 32:
            pairs.append((kid, key))
        else:
            print(f"Invalid format: {line}")
    return pairs

print("Vault Key Uploader\n")

host    = input("Vault Host: ").strip()
token   = input("Token: ").strip()
service = input("Service: ").strip()

if len(sys.argv) > 1:
    file_path = sys.argv[1].strip().strip('"')
    print(f"File: {file_path}")
    with open(file_path, encoding="utf-8") as f:
        pairs = parse_pairs(f.read())
else:
    print("Paste keys (KID:KEY), separated by newlines or semicolons,")
    print("or drag and drop a .txt file.\n")
    raw = input("Keys: ").strip()
    if raw.endswith(".txt") and len(raw) < 260:
        try:
            with open(raw.strip('"'), encoding="utf-8") as f:
                pairs = parse_pairs(f.read())
        except FileNotFoundError:
            pairs = parse_pairs(raw)
    else:
        pairs = parse_pairs(raw)

print(f"\nPushing {len(pairs)} key(s) to '{service}'...\n")

inserted = 0
cached = 0
for kid, key in pairs:
    result = insert_key(host, token, kid, key, service)
    if result:
        print(f"Posted  {kid}:{key}")
        inserted += 1
    else:
        print(f"Cached  {kid}:{key}")
        cached += 1

print(f"\nDone! {inserted} inserted, {cached} already existed.")