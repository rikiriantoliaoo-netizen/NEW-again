#!/bin/bash
# Jalankan WhatsApp (Baileys) service di background, lalu bot Telegram.
node baileys_server.js &
exec python3 main.py
