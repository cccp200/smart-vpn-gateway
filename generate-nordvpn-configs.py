#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import base64

CONFIG_DIR = "/home/cp/wireguard/config"
COUNTRIES = {
    "albanien": 2,
    "danmark": 58,
    "sverige": 208
}

def get_private_key_from_token(token):
    url = "https://api.nordvpn.com/v1/users/services/credentials"
    auth_header = "Basic " + base64.b64encode(f"token:{token}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": auth_header, "User-Agent": "curl/7.68.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return data.get("nordlynx_private_key")
    except Exception as e:
        print(f"Fejl ved hentning af privat nøgle fra NordVPN API: {e}", file=sys.stderr)
        return None

def get_server_info(country_id):
    url = f"https://api.nordvpn.com/v1/servers/recommendations?filters[country_id]={country_id}&filters[servers_technologies][id]=35&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
    with urllib.request.urlopen(req) as resp:
        servers = json.loads(resp.read().decode())
        if not servers:
            return None
        s = servers[0]
        pubkey = None
        for tech in s.get("technologies", []):
            if tech.get("identifier") == "wireguard_udp":
                for meta in tech.get("metadata", []):
                    if meta.get("name") == "public_key":
                        pubkey = meta.get("value")
        return {
            "name": s.get("name"),
            "hostname": s.get("hostname"),
            "station": s.get("station"),
            "pubkey": pubkey
        }

def write_config(country_name, private_key, server_info):
    conf_dir = os.path.join(CONFIG_DIR, country_name)
    os.makedirs(conf_dir, exist_ok=True)
    conf_path = os.path.join(conf_dir, "wg0.conf")
    
    content = f"""[Interface]
PrivateKey = {private_key}
Address = 10.5.0.2/32
DNS = 103.86.96.100, 103.86.99.100

[Peer]
PublicKey = {server_info['pubkey']}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = {server_info['station']}:51820
PersistentKeepalive = 25
"""
    with open(conf_path, "w") as f:
        f.write(content)
    os.chmod(conf_path, 0o600)
    print(f"[OK] Oprettede {conf_path} ({server_info['name']} - {server_info['hostname']})")

def write_smart_gateway_config(private_key, servers):
    gw_dir = os.path.join(os.path.dirname(CONFIG_DIR), "smart-gateway")
    os.makedirs(gw_dir, exist_ok=True)
    cfg_path = os.path.join(gw_dir, "config.json")
    
    cfg = {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [
                {"tag": "dns-remote", "type": "udp", "server": "1.1.1.1", "server_port": 53}
            ]
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": "tun0",
                "address": ["172.19.0.1/30"],
                "auto_route": True,
                "auto_redirect": True,
                "strict_route": False,
                "stack": "mixed"
            }
        ],
        "endpoints": [
            {
                "type": "wireguard",
                "tag": "albanien",
                "address": ["10.5.0.2/32"],
                "private_key": private_key,
                "peers": [{
                    "address": servers["albanien"]["station"],
                    "port": 51820,
                    "public_key": servers["albanien"]["pubkey"],
                    "allowed_ips": ["0.0.0.0/0", "::/0"]
                }]
            },
            {
                "type": "wireguard",
                "tag": "danmark",
                "address": ["10.5.0.2/32"],
                "private_key": private_key,
                "peers": [{
                    "address": servers["danmark"]["station"],
                    "port": 51820,
                    "public_key": servers["danmark"]["pubkey"],
                    "allowed_ips": ["0.0.0.0/0", "::/0"]
                }]
            },
            {
                "type": "wireguard",
                "tag": "sverige",
                "address": ["10.5.0.2/32"],
                "private_key": private_key,
                "peers": [{
                    "address": servers["sverige"]["station"],
                    "port": 51820,
                    "public_key": servers["sverige"]["pubkey"],
                    "allowed_ips": ["0.0.0.0/0", "::/0"]
                }]
            }
        ],
        "outbounds": [{"type": "direct", "tag": "direct"}],
        "route": {
            "auto_detect_interface": True,
            "rules": [
                {"action": "sniff"},
                {"protocol": "dns", "action": "hijack-dns"},
                {"ip_is_private": True, "outbound": "direct"},
                {
                    "domain_suffix": [
                        "youtube.com", "googlevideo.com", "youtu.be",
                        "ytimg.com", "youtube-nocookie.com",
                        "youtubei.googleapis.com", "yt3.ggpht.com"
                    ],
                    "outbound": "albanien"
                },
                {
                    "domain_suffix": ["svt.se", "svtplay.se", "svtstatic.se", "svtid.se"],
                    "outbound": "sverige"
                },
                {
                    "domain_suffix": ["dr.dk"],
                    "outbound": "danmark"
                }
            ],
            "final": "direct"
        }
    }
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[OK] Opdaterede Smart Gateway konfiguration: {cfg_path}")

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print("Brug: python3 generate-nordvpn-configs.py [NORDVPN_ACCESS_TOKEN_ELLER_PRIVATE_KEY]")
        print("Hvis intet argument gives, spørger scriptet interaktivt.")
        sys.exit(0)

    token_or_key = None
    if len(sys.argv) > 1:
        token_or_key = sys.argv[1].strip()
    else:
        token_or_key = input("Indtast dit NordVPN Access Token (eller direkte din NordLynx Private Key): ").strip()

    if not token_or_key:
        print("Ingen token eller nøgle angivet.", file=sys.stderr)
        sys.exit(1)

    private_key = None
    # Tjek om det allerede er en base64-kodet privat nøgle (typisk 44 tegn med '=')
    if len(token_or_key) == 44 and token_or_key.endswith("="):
        private_key = token_or_key
        print("Modtog direkte NordLynx Private Key.")
    else:
        print("Henter privat nøgle via dit NordVPN Access Token...")
        private_key = get_private_key_from_token(token_or_key)
        if not private_key:
            print("Kunne ikke hente din private nøgle. Kontrollér om dit token er gyldigt.", file=sys.stderr)
            sys.exit(1)
        print("Privat nøgle hentet med succes!")

    server_dict = {}
    for country_name, country_id in COUNTRIES.items():
        print(f"Finder bedste WireGuard-server for {country_name.capitalize()}...")
        server = get_server_info(country_id)
        if not server or not server["pubkey"]:
            print(f"Fejl: Kunne ikke finde WireGuard server for {country_name}", file=sys.stderr)
            continue
        write_config(country_name, private_key, server)
        server_dict[country_name] = server

    if len(server_dict) == len(COUNTRIES):
        write_smart_gateway_config(private_key, server_dict)

    print("\nFærdig! Du kan nu køre:")
    print("  cd /home/cp/wireguard && docker compose up -d")

if __name__ == "__main__":
    main()
