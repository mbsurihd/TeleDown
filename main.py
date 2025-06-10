import sqlite3
from datetime import datetime
from pathlib import Path

from pyrogram.client import Client
from pyrogram.types import Chat, Message
from pyrogram.enums.chat_type import ChatType
from pyrogram.enums.message_media_type import MessageMediaType

from ProgressBar import CreateProgressBar, TimedPromptKey

App: Client
DatabaseConnection: sqlite3.Connection
Database: sqlite3.Cursor
LastUpdate: datetime
CHAT: Chat
DEST_DIR: Path
CHAT_ID: int

DB_FILE = "./TeleDown.db"
DOWNLOAD_TYPES = [MessageMediaType.PHOTO, MessageMediaType.VIDEO, MessageMediaType.VOICE, MessageMediaType.DOCUMENT, MessageMediaType.VIDEO_NOTE, MessageMediaType.AUDIO, MessageMediaType.ANIMATION]

async def last_update (chat: Chat):
    chat_history = await App.get_chat_history(chat.id, limit = 1)
    if chat_history != None:
        async for message in chat_history:
            last_message = message
            return last_message.date
    return datetime.fromtimestamp(0)

def db_init():
    DatabaseConnection = sqlite3.connect(DB_FILE)
    Database = DatabaseConnection.cursor()
    _ = Database.executescript("""
CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY, last_update DATETIME);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, file TEXT, size INTEGER, complete BOOLEAN, FORIEGN KEY (chat_id) REFERENCES chats(id));
    """)
    DatabaseConnection.commit()

#Helper
def message_media_size(message: Message):
    if message.media == MessageMediaType.PHOTO:
        return message.photo.file_size
    elif message.media == MessageMediaType.VIDEO:
        return message.video.file_size
    elif message.media == MessageMediaType.ANIMATION:
        return message.animation.file_size
    elif message.media == MessageMediaType.AUDIO:
        return message.audio.file_size
    elif message.media == MessageMediaType.VIDEO_NOTE:
        return message.video_note.file_size
    elif message.media == MessageMediaType.DOCUMENT:
        return message.document.file_size
    elif message.media == MessageMediaType.VOICE:
        return message.voice.file_size
    else:
        return 0

async def update_message_db(chat: Chat):
    chat_history = await App.get_chat_history(chat.id)
    if chat_history != None:
        async for message in chat_history:
            if message.media in DOWNLOAD_TYPES:
                res = Database.execute(f"SELECT id FROM messages WHERE id = {message.id} AND chat_id = {chat.id}")
                if res.fetchone() is None:
                    _ =  Database.execute(f"INSERT INTO messages(id, chat_id, size, complete) VALUES({message.id}, {chat.id}, {message_media_size(message)}, FALSE)")
                else:
                    break
        _ = Database.execute(f"UPDATE chats SET last_update = '{LastUpdate.isoformat()}' WHERE id = {chat.id}")
        DatabaseConnection.commit()

def index_directory(index_root: Path):
    _= Database.execute("DROP TABLE IF EXISTS files")
    _ = Database.execute("CREATE TABLE IF NOT EXISTS files(file TEXT NOT NULL, size NOT NULL INTEGER)")

    if not index_root.exists():
        return None
    for entry in index_root.iterdir():
        if not entry.is_dir():
            _ = Database.execute(f"INSERT INTO files(file , size) VALUES({str(entry.absolute())}, {entry.stat().st_size})")
    DatabaseConnection.commit()

def update_file_db():
    _ = Database.execute("""
    UPDATE messages
    SET
        complete = FALSE
    WHERE id IN (
        SELECT messages.id
        FROM messages AS m
        JOIN files AS f
        ON m.file == f.file 
        AND m.size > f.size
    );
    UPDATE messages
    SET
        complete = TRUE
    WHERE id IN (
        SELECT messages.id
        FROM messages AS m
        JOIN files AS f
        ON m.file == f.file 
        AND m.size <= f.size
    );
    """)

#Helper
def narrow_type[T](value: T | object, default: T) -> T:
    if isinstance(value, type(default)):
        return value
    else:
        return default

def CreateAsyncProgressBar(Background: int, Foreground: int, Text: int):
    pbcb = CreateProgressBar(Background, Foreground, Text)

    async def callback(current: float, total: float):
        return pbcb(current / total)
    return callback


async def main():
    #Initilization
    _CHAT = await App.get_chat(CHAT_ID)
    CHAT = narrow_type(_CHAT, Chat(id = 0, type = ChatType.CHANNEL))
    db_init()
    LastUpdate = await last_update(CHAT)

    res = Database.execute(f"SELECT id FROM chats WHERE id = {CHAT.id}")
    if res.fetchone() is None:
        _ = Database.execute(f"INSERT INTO chats(id, last_update) VALUES({CHAT.id}, '{datetime.fromtimestamp(0).isoformat()}')")
        DatabaseConnection.commit()
    res = Database.execute(f"SELECT last_update FROM chats WHERE id = {CHAT.id}")
    chatdb_update = datetime.fromisoformat(res.fetchone()[0])
    if LastUpdate > chatdb_update:
        await update_message_db(CHAT)
    index_directory(DEST_DIR)
    update_file_db()
    res = Database.execute(f"SELECT id FROM messages WHERE completed = FALSE AND chat_id = {CHAT.id}")
    new_msgs: list[int] = [f[0] for f in res.fetchall()]
    for msg_id in new_msgs:
        message = narrow_type(await App.get_messages(CHAT.id, msg_id), Message(id = 0))
        progbar = CreateAsyncProgressBar(18, 232, 251)
        _dpath = await App.download_media(str(DEST_DIR), progress = progbar)
        media_path: Path
        if not _dpath is None:
            media_path = Path(narrow_type(_dpath, ""))
            res = Database.execute(f"SELECT size FROM messages WHERE id = {message.id} AND chat_id = {CHAT.id}")
            size: int = res.fetchone()[0]
            if media_path.stat().st_size >= size:
                _ = Database.execute(f"UPDATE messages SET complete = TRUE file = {str(media_path)} WHERE id = {message.id} AND chat_id = {CHAT.id}")
            else:
                print(f"Downloading {str(media_path)} failed")
        else:
            print("Download failed")
        if TimedPromptKey(5, 'x'):
            break


