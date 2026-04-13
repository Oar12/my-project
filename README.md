# CONNECT
ssh pi@tradingbot.local
ssh pi@100.x.x.x   # (Tailscale - recommended)

# BOT STATUS
systemctl status trend_bot.service
systemctl is-active trend_bot.service

# START / STOP / RESTART BOT
sudo systemctl start trend_bot.service
sudo systemctl stop trend_bot.service
sudo systemctl restart trend_bot.service

# LIVE LOGS (BOT)
journalctl -u trend_bot.service -f -o cat

# TRADE LOG FILE
tail -f ~/mybot/trade_log.txt
tail -n 50 ~/mybot/trade_log.txt

# SYSTEM HEALTH
uptime
free -h
df -h
top

# TEMPERATURE / THROTTLING
vcgencmd measure_temp
vcgencmd get_throttled

# NETWORK (TAILSCALE)
tailscale ip -4
tailscale status

# UPDATE CODE + RESTART BOT
cd ~/mybot && git pull
sudo systemctl restart trend_bot.service

# EMERGENCY CHECK (FULL STATUS)
echo "=== SYSTEM ===" && uptime && \
echo "=== RAM ===" && free -h && \
echo "=== DISK ===" && df -h && \
echo "=== BOT ===" && systemctl is-active trend_bot.service && \
echo "=== TEMP ===" && vcgencmd measure_temp && \
echo "=== TAILSCALE ===" && tailscale ip -4