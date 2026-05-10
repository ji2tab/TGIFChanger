#!/bin/bash
echo "🗑️ Uninstalling TGIFChanger-Py..."
if command -v rpi-rw >/dev/null 2>&1; then sudo rpi-rw; fi

sudo systemctl stop tgifchanger-py tgifchanger-web 2>/dev/null || true
sudo systemctl disable tgifchanger-py tgifchanger-web 2>/dev/null || true
sudo rm -f /etc/systemd/system/tgifchanger-*.service
sudo rm -f /usr/local/bin/tg_change
sudo rm -rf /opt/tgifchanger-py

FW_FILE="/usr/local/bin/pistar-firewall"
if [ -f "$FW_FILE" ]; then
    sudo sed -i '/dport 8080/d' "$FW_FILE"
fi
sudo iptables -D INPUT -p tcp --dport 8080 -j ACCEPT 2>/dev/null || true
sudo systemctl daemon-reload
echo "✅ Uninstalled."
