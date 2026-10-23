# Group Event Calendar Bot

Python Telegram group calendar using aiogram 3 + SQLite. Calendars are isolated per Telegram chat.

## Commands

- `/add` – add an event interactively
- `/add Meeting; 24.10.2026; 14:00; Room 305; Discussion` – add an event in one message
- `/events`, `/calendar`, `/info ID`, `/edit ID`, `/delete ID`, `/cancel`, `/help`

## Deployment to Bothost

1. Create a bot at https://bothost.ru/create-bot.php with Telegram, aiogram and GitHub URL for this repository. Select branch `main` and entrypoint `bot.py`.
2. Set the bot token via Bothost's protected token configuration, **never commit it to GitHub**.
3. Install dependencies from `requirements.txt`.
4. Set `TIMEZONE=Asia/Bishkek` and `DB_PATH=/app/data/events.sqlite3` **only if** this is persistent storage on your account. Verify persistence in Bothost documentation/settings; otherwise configure an external persistent volume/database.
5. Stop other copies of the polling bot on Mac/PythonAnywhere to avoid conflicts.
6. Test `/help`, `/add`, `/events` and `/calendar` in each group.

Your SQLite file contains the actual events and is not stored in GitHub. Back it up before changing hosts. For guided entry, disable Group Privacy through BotFather if the bot cannot read ordinary group messages.
