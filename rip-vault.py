import requests
session = requests.Session()
session.headers.update({"User-Agent": "unshackle v4.0.0"})
api_session_id = None

def get_key(host: str, token: str, kid: str, service: str) -> str | None:
    global api_session_id
    params = {"kid": kid, "service": service.lower()}
    if api_session_id:
        params["session_id"] = api_session_id
    r = session.post(host, json={"method": "GetKey", "params": params, "token": token})
    res = r.json()
    if isinstance(res.get("message"), dict):
        if sid := res["message"].get("session_id"):
            api_session_id = sid
        keys = res["message"].get("keys", [])
        for entry in keys:
            if isinstance(entry, str) and ":" in entry:
                return entry.split(":", 1)[1]
            elif isinstance(entry, dict):
                return entry.get("key")
    return None

print("Vault Ripper\n")

host     = input("Vault host: ").strip()
token    = input("Token: ").strip()
service  = input("Service: ").strip()
kids_file = input("KIDs file path: ").strip()
output   = input("Output file: ").strip() or "found_keys.txt"

kids = []
with open(kids_file, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        kid = line.split(":")[0].strip().lower()
        if len(kid) == 32:
            kids.append(kid)
        else:
            print(f"Bad KID: {kid}")

print(f"\nLoaded {len(kids)} KID(s), querying service '{service}'...\n")

found = []
for kid in kids:
    key = get_key(host, token, kid, service)
    if key:
        print(f"HIT  {kid}:{key}")
        found.append(f"{kid}:{key}")
    else:
        print(f"MISS {kid}")

if found:
    with open(output, "w") as f:
        f.write("\n".join(found))
    print(f"\nSaved {len(found)}/{len(kids)} keys to {output}")
else:
    print("\nNo keys found.")