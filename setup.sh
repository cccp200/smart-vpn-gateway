#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  Apple TV Smart VPN Gateway - Automatisk Installationsscript"
echo "=========================================================="
echo ""

# 1. Tjek og installer Docker hvis det mangler
if ! command -v docker &> /dev/null; then
    echo "[1/4] Docker er ikke installeret. Installerer Docker nu..."
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
    sudo usermod -aG docker "$USER"
    rm -f /tmp/get-docker.sh
    echo "[OK] Docker installeret."
else
    echo "[1/4] Docker er allerede installeret."
fi

# 2. Aktiver IP Forwarding på systemet
echo "[2/4] Sikrer at IP-forwarding er aktiveret..."
sudo sysctl -w net.ipv4.ip_forward=1 > /dev/null
echo "net.ipv4.ip_forward = 1" | sudo tee /etc/sysctl.d/99-ip-forward.conf > /dev/null
echo "[OK] IP-forwarding aktiveret og gjort permanent."

# 3. Kør script til at hente NordVPN nøgler og oprette konfigurationer
echo "[3/4] Genererer VPN- og Smart Gateway-konfiguration..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -n "$1" ]; then
    python3 "$SCRIPT_DIR/generate-nordvpn-configs.py" "$1"
else
    python3 "$SCRIPT_DIR/generate-nordvpn-configs.py"
fi

# 4. Start Smart Gateway
echo "[4/4] Starter Smart Gateway containeren..."
cd "$SCRIPT_DIR/smart-gateway"
sudo docker compose up -d

echo ""
echo "=========================================================="
echo "  Installation fuldført!"
echo "=========================================================="
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo "Din Raspberry Pi's IP-adresse er: $LOCAL_IP"
echo ""
echo "Indstil nu dit Apple TV:"
echo "  1. Gå til Indstillinger -> Netværk -> Konfigurer IP -> Manuelt"
echo "     - Router (Gateway): $LOCAL_IP"
echo "  2. Konfigurer DNS -> Manuelt"
echo "     - DNS-server: $LOCAL_IP"
echo ""
echo "Se live logs med:"
echo "  cd $SCRIPT_DIR/smart-gateway && sudo docker compose logs -f"
echo "=========================================================="
