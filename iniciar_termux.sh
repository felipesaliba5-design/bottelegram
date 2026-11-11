#!/data/data/com.termux/files/usr/bin/bash
# Watchdog para manter o bot rodando 24/7 no Termux (Android)

set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
mkdir -p logs

if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] termux-wake-lock ativado." | tee -a logs/watchdog.log
fi

trap '
    echo "[$(date "+%Y-%m-%d %H:%M:%S")] Encerrando watchdog..." | tee -a logs/watchdog.log
    if command -v termux-wake-unlock >/dev/null 2>&1; then
        termux-wake-unlock
    fi
    exit 0
' INT TERM

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iniciando bot.py..." | tee -a logs/watchdog.log
    python bot.py
    codigo=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] bot.py finalizou (codigo=$codigo). Reiniciando em 5s..." | tee -a logs/watchdog.log
    sleep 5
done
