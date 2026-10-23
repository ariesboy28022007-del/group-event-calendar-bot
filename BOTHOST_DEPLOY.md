# Bothost setup

- Git URL: `https://github.com/ariesboy28022007-del/group-event-calendar-bot`
- Git branch: `main`
- Language: Python
- Framework/library: aiogram
- Entry point: `bot.py`
- Dependencies: `requirements.txt`
- Telegram token: supply **only** in BotHost's secret/token setting
- Timezone environment variable: `TIMEZONE=Asia/Bishkek`
- Data: SQLite needs a persistent writable directory; if `/app/data` is confirmed persistent set `DB_PATH=/app/data/events.sqlite3`.
- Ensure only a single running bot process.

**Note:** Code deploy is not the same as data migration. Move old events SQLite separately and make backups.
