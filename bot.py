import asyncio
import calendar
import html
import logging
import os
from datetime import datetime
from pathlib import Path

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = Path(os.getenv("DB_PATH", "events.sqlite3"))
TZ = os.getenv("TIMEZONE", "Asia/Bishkek")
router = Router()

class Add(StatesGroup):
    title = State()
    date = State()
    time = State()
    place = State()
    description = State()

class Edit(StatesGroup):
    value = State()

async def db_init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,
            creator_id INTEGER NOT NULL, title TEXT NOT NULL, starts_at TEXT NOT NULL,
            place TEXT DEFAULT '', description TEXT DEFAULT ''
        )""")
        await db.execute("CREATE INDEX IF NOT EXISTS event_chat_date ON events(chat_id,starts_at)")
        await db.commit()

async def get_event(chat_id, event_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE chat_id=? AND id=?", (chat_id,event_id)) as cur:
            return await cur.fetchone()

async def create_event(chat_id, creator_id, title, starts_at, place, description):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("INSERT INTO events(chat_id,creator_id,title,starts_at,place,description) VALUES(?,?,?,?,?,?)",
                               (chat_id,creator_id,title,starts_at,place,description))
        await db.commit()
        return cur.lastrowid

def event_text(e):
    dt=datetime.fromisoformat(e["starts_at"])
    return (f"<b>#{e['id']} · {html.escape(e['title'])}</b>\n"
            f"📅 {dt:%d.%m.%Y} {dt:%H:%M} ({html.escape(TZ)})\n"
            f"📍 {html.escape(e['place'] or 'Не указано')}\n"
            f"📝 {html.escape(e['description'] or 'Без описания')}")

def group(message):
    return message.chat.type in ("group","supergroup")

async def ensure_group(message):
    if not group(message):
        await message.answer("Команды календаря работают в групповых чатах.")
        return False
    return True

def parse_date(t):
    return datetime.strptime(t.strip(),"%d.%m.%Y").strftime("%Y-%m-%d")

def parse_time(t):
    return datetime.strptime(t.strip(),"%H:%M").strftime("%H:%M")

def quick(raw):
    p=[x.strip() for x in raw.split(";")]
    if not 3 <= len(p) <= 5:
        raise ValueError("Нужно от 3 до 5 полей через ;")
    title,date,clock=p[:3]
    if not 1 <= len(title) <= 120: raise ValueError("Название: от 1 до 120 символов")
    place=p[3] if len(p)>3 and p[3]!="-" else ""
    desc=p[4] if len(p)>4 and p[4]!="-" else ""
    if len(place)>200 or len(desc)>1500: raise ValueError("Место или описание слишком длинное")
    return title,parse_date(date)+"T"+parse_time(clock)+":00",place,desc

async def owner_or_admin(message,e):
    if message.from_user and message.from_user.id==e["creator_id"]: return True
    if not message.from_user: return False
    try:
        member=await message.bot.get_chat_member(message.chat.id,message.from_user.id)
        return member.status in ("administrator","creator")
    except Exception: return False

@router.message(Command("help","start"))
async def help_command(message:Message):
    await message.answer(
        "📅 <b>Календарь группы</b>\n"
        "/add — создать событие пошагово\n"
        "/add Название; 24.10.2026; 14:00; Место; Описание — сразу\n"
        "/events — ближайшие мероприятия\n"
        "/calendar — календарь по месяцам\n"
        "/info ID — информация\n"
        "/edit ID — изменить событие\n"
        "/delete ID — удалить событие\n"
        "/cancel — отмена\nКаждая группа видит только свои мероприятия.")

@router.message(Command("cancel"))
async def cancel(message:Message,state:FSMContext):
    await state.clear()
    await message.answer("Действие отменено.")

@router.message(Command("add"))
async def add(message:Message,state:FSMContext):
    if not await ensure_group(message): return
    args=(message.text or "").split(maxsplit=1)
    await state.clear()
    if len(args)==2:
        try: title,at,place,desc=quick(args[1])
        except ValueError as err:
            return await message.answer(f"⚠️ {html.escape(str(err))}\nПример:\n<code>/add Встреча; 24.10.2026; 14:00; Аудитория 305; Описание</code>")
        eid=await create_event(message.chat.id,message.from_user.id,title,at,place,desc)
        return await message.answer("✅ Событие создано!\n\n"+event_text(await get_event(message.chat.id,eid)))
    await state.set_state(Add.title)
    await message.answer("Как называется мероприятие? /cancel — отменить")

@router.message(Add.title)
async def add_title(message:Message,state:FSMContext):
    title=(message.text or "").strip()
    if not 1<=len(title)<=120:return await message.answer("Введите название (до 120 символов)")
    await state.update_data(title=title)
    await state.set_state(Add.date)
    await message.answer("Дата? Например 24.10.2026")

@router.message(Add.date)
async def add_date(message:Message,state:FSMContext):
    try: date=parse_date(message.text or "")
    except ValueError:return await message.answer("Неверная дата. Формат: 24.10.2026")
    await state.update_data(date=date)
    await state.set_state(Add.time)
    await message.answer("Время? Например 14:00")

@router.message(Add.time)
async def add_time(message:Message,state:FSMContext):
    try: tm=parse_time(message.text or "")
    except ValueError:return await message.answer("Неверное время. Формат: 14:00")
    await state.update_data(time=tm)
    await state.set_state(Add.place)
    await message.answer("Место? Для пропуска напишите -")

@router.message(Add.place)
async def add_place(message:Message,state:FSMContext):
    value=(message.text or "").strip()
    if len(value)>200:return await message.answer("Место слишком длинное")
    await state.update_data(place="" if value=="-" else value)
    await state.set_state(Add.description)
    await message.answer("Описание? Для пропуска напишите -")

@router.message(Add.description)
async def add_description(message:Message,state:FSMContext):
    value=(message.text or "").strip()
    if len(value)>1500:return await message.answer("Описание слишком длинное")
    data=await state.get_data()
    eid=await create_event(message.chat.id,message.from_user.id,data["title"],data["date"]+"T"+data["time"]+":00",data["place"],"" if value=="-" else value)
    await state.clear()
    await message.answer("✅ Событие создано!\n\n"+event_text(await get_event(message.chat.id,eid)))

@router.message(Command("events"))
async def events(message:Message):
    if not await ensure_group(message):return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory=aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE chat_id=? AND starts_at>=? ORDER BY starts_at LIMIT 10",
                              (message.chat.id,datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))) as cur:
            rows=await cur.fetchall()
    if not rows:return await message.answer("📭 Ближайших мероприятий нет. Добавь через /add")
    await message.answer("📅 <b>Ближайшие мероприятия</b>\n\n"+"\n\n".join(event_text(e) for e in rows))

def id_arg(message):
    try:return int((message.text or "").split()[1])
    except (IndexError,ValueError):return None

@router.message(Command("info"))
async def info(message:Message):
    if not await ensure_group(message):return
    event_id=id_arg(message)
    if event_id is None:return await message.answer("Пример: /info 3")
    e=await get_event(message.chat.id,event_id)
    await message.answer(event_text(e) if e else "Событие не найдено.")

@router.message(Command("edit"))
async def edit(message:Message,state:FSMContext):
    if not await ensure_group(message):return
    event_id=id_arg(message)
    if event_id is None:return await message.answer("Пример: /edit 3")
    e=await get_event(message.chat.id,event_id)
    if not e:return await message.answer("Событие не найдено.")
    if not await owner_or_admin(message,e):return await message.answer("Изменять может автор или администратор.")
    await state.clear()
    await state.update_data(event_id=event_id)
    keyboard=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Название",callback_data=f"editfield:{event_id}:title"),
         InlineKeyboardButton(text="Дата и время",callback_data=f"editfield:{event_id}:starts_at")],
        [InlineKeyboardButton(text="Место",callback_data=f"editfield:{event_id}:place"),
         InlineKeyboardButton(text="Описание",callback_data=f"editfield:{event_id}:description")]])
    await message.answer(event_text(e)+"\n\nЧто изменить?",reply_markup=keyboard)

@router.callback_query(F.data.startswith("editfield:"))
async def edit_field(query:CallbackQuery,state:FSMContext):
    _,eid,field=query.data.split(":")
    e=await get_event(query.message.chat.id,int(eid))
    if not e:return await query.answer("Не найдено",show_alert=True)
    try:
        m=await query.bot.get_chat_member(query.message.chat.id,query.from_user.id)
        allowed=e["creator_id"]==query.from_user.id or m.status in ("administrator","creator")
    except Exception: allowed=e["creator_id"]==query.from_user.id
    if not allowed:return await query.answer("Недостаточно прав",show_alert=True)
    await state.set_state(Edit.value)
    await state.update_data(event_id=int(eid),field=field)
    await query.answer()
    await query.message.answer("Отправь новое значение. Для даты: 24.10.2026 14:00. /cancel — отмена")

@router.message(Edit.value)
async def edit_value(message:Message,state:FSMContext):
    data=await state.get_data()
    e=await get_event(message.chat.id,data["event_id"])
    if not e or not await owner_or_admin(message,e):
        await state.clear()
        return await message.answer("Нет доступа к событию.")
    field=data["field"]
    value=(message.text or "").strip()
    try:
        if field=="starts_at":value=datetime.strptime(value,"%d.%m.%Y %H:%M").strftime("%Y-%m-%dT%H:%M:00")
        elif field=="title" and not 1<=len(value)<=120:raise ValueError()
        elif field=="place" and len(value)>200:raise ValueError()
        elif field=="description" and len(value)>1500:raise ValueError()
    except ValueError:return await message.answer("Неверный формат или слишком длинное значение. Попробуй снова.")
    if value=="-" and field in ("place","description"):value=""
    if field not in ("starts_at","title","place","description"):return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE events SET {field}=? WHERE id=? AND chat_id=?",(value,e["id"],message.chat.id))
        await db.commit()
    await state.clear()
    await message.answer("✅ Обновлено!\n"+event_text(await get_event(message.chat.id,e["id"])))

@router.message(Command("delete"))
async def delete(message:Message):
    if not await ensure_group(message):return
    event_id=id_arg(message)
    if event_id is None:return await message.answer("Пример: /delete 3")
    e=await get_event(message.chat.id,event_id)
    if not e:return await message.answer("Событие не найдено.")
    if not await owner_or_admin(message,e):return await message.answer("Удалять может автор или администратор.")
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Удалить",callback_data=f"del:{event_id}"),
                                               InlineKeyboardButton(text="Отмена",callback_data="delcancel")]])
    await message.answer(event_text(e)+"\nУдалить мероприятие?",reply_markup=kb)

@router.callback_query(F.data=="delcancel")
async def delcancel(query:CallbackQuery):
    await query.answer("Отменено")
    await query.message.edit_reply_markup(reply_markup=None)

@router.callback_query(F.data.startswith("del:"))
async def del_confirm(query:CallbackQuery):
    event_id=int(query.data.split(":")[1])
    e=await get_event(query.message.chat.id,event_id)
    if not e:return await query.answer("Уже удалено",show_alert=True)
    try:
        m=await query.bot.get_chat_member(query.message.chat.id,query.from_user.id)
        allowed=e["creator_id"]==query.from_user.id or m.status in ("administrator","creator")
    except Exception: allowed=e["creator_id"]==query.from_user.id
    if not allowed:return await query.answer("Недостаточно прав",show_alert=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM events WHERE id=? AND chat_id=?",(event_id,query.message.chat.id))
        await db.commit()
    await query.answer("Удалено")
    await query.message.edit_text("🗑 Мероприятие удалено.")

def month_keyboard(year,month):
    lines=[[InlineKeyboardButton(text="Пн",callback_data="noop"),
            InlineKeyboardButton(text="Вт",callback_data="noop"),
            InlineKeyboardButton(text="Ср",callback_data="noop"),
            InlineKeyboardButton(text="Чт",callback_data="noop"),
            InlineKeyboardButton(text="Пт",callback_data="noop"),
            InlineKeyboardButton(text="Сб",callback_data="noop"),
            InlineKeyboardButton(text="Вс",callback_data="noop")]]
    for week in calendar.monthcalendar(year,month):
        lines.append([InlineKeyboardButton(text=str(day) if day else "·",callback_data=f"day:{year}:{month}:{day}" if day else "noop") for day in week])
    a=datetime(year,month,1)
    prior=(a.replace(day=1) - __import__("datetime").timedelta(days=1))
    nxt=datetime(year+1,1,1) if month==12 else datetime(year,month+1,1)
    lines.append([InlineKeyboardButton(text="◀",callback_data=f"month:{prior.year}:{prior.month}"),
                  InlineKeyboardButton(text="▶",callback_data=f"month:{nxt.year}:{nxt.month}")])
    return InlineKeyboardMarkup(inline_keyboard=lines)

@router.message(Command("calendar"))
async def calendar_cmd(message:Message):
    if not await ensure_group(message):return
    now=datetime.now()
    await message.answer(f"📅 <b>{now:%m.%Y}</b> — выбери день",reply_markup=month_keyboard(now.year,now.month))

@router.callback_query(F.data.startswith("month:"))
async def calendar_month(query:CallbackQuery):
    _,y,m=query.data.split(":")
    await query.message.edit_text(f"📅 <b>{int(m):02}.{y}</b> — выбери день",reply_markup=month_keyboard(int(y),int(m)))
    await query.answer()

@router.callback_query(F.data.startswith("day:"))
async def calendar_day(query:CallbackQuery):
    _,y,m,d=query.data.split(":")
    day=f"{int(y):04}-{int(m):02}-{int(d):02}"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory=aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE chat_id=? AND substr(starts_at,1,10)=? ORDER BY starts_at",(query.message.chat.id,day)) as cur:
            rows=await cur.fetchall()
    await query.answer()
    await query.message.answer("\n\n".join(event_text(e) for e in rows) if rows else "На этот день событий нет.")

@router.callback_query(F.data=="noop")
async def noop(query:CallbackQuery):await query.answer()

async def main():
    if not TOKEN:raise RuntimeError("Нужен BOT_TOKEN в настройках хостинга или .env")
    await db_init()
    bot=Bot(TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp=Dispatcher()
    dp.include_router(router)
    await bot.set_my_commands([BotCommand(command=c,description=d) for c,d in [
        ("add","Добавить мероприятие"),("events","Ближайшие события"),("calendar","Календарь"),
        ("info","Информация о событии"),("edit","Изменить событие"),("delete","Удалить событие"),
        ("cancel","Отменить ввод"),("help","Помощь")]])
    await dp.start_polling(bot)

if __name__=="__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
