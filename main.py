import sqlite3
from pathlib import Path
from datetime import datetime
import json
from typing import Any

from pyrogram.types import Chat, Message
from pyrogram.client import Client
from pyrogram.enums.chat_type import ChatType

from ProgressBar import CreateProgressBar, TimedPromptKey

#Debug
import pdb

#Intialization [Sync]
def DBInit(DB_FILE: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    _ = cursor .executescript("""
    CREATE TABLE IF NOT EXISTS chats(
        id INTEGER PRIMARY KEY, 
        last_update DATETIME
    );
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY, 
        chat_id INTEGER NOT NULL, 
        file TEXT, size INTEGER, 
        complete BOOLEAN, 
        FOREIGN KEY (chat_id) REFERENCES chats(id)
    );
    """)
    conn.commit()
    return conn

#Helper [Sync]
def MessageMediaSize(MESSAGE: Message) -> int:
    _media_type = MESSAGE.media.__str__().split('.')[1].lower()
    return MESSAGE.__getattribute__(_media_type).file_size

def IndexDirectory(IndexRoot: str, Database: sqlite3.Connection | None):
    if Database is None:
        Database = sqlite3.connect(":memory:")
    _cursor = Database.cursor()
    _ = _cursor.execute("DROP TABLE IF EXISTS files")
    _ = _cursor.execute("""
    CREATE TABLE IF NOT EXISTS files(
        file TEXT NOT NULL,
        size INTEGER NOT NULL
    )
    """)

    _index_path = Path(IndexRoot)
    for _e in _index_path.iterdir():
        if not _e.is_dir():
            _ = _cursor.execute(f"""
            INSERT INTO files(file, size)
            VALUES(
                '{str(_e.absolute())}',
                {_e.stat().st_size}
            );
            """)
    Database.commit()
    return Database

def UpdateFileDB(Database: sqlite3.Connection):
    _cursor = Database.cursor()
    _ = _cursor.executescript(f"""
    UPDATE messages
    SET 
        complete = 
    CASE
        WHEN files.file IS NOT NULL AND files.size = messages.size THEN 1
        ELSE 0
    END
    FROM files
    WHERE files.file = messages.file
    ;

    UPDATE messages
    SET complete = 0
    WHERE file NOT IN (SELECT file FROM files)
    ;
    """)
    Database.commit()
    return None

def NarrowType[T](value: T | object, default: T) ->T:
    if isinstance(value, type(default)):
        return value
    else:
        return default

#Initilization [Async]
async def GetLastUpdateTime(App: Client, CHAT: Chat):
    async for _m in App.get_chat_history(CHAT.id, limit = 1):
        return _m.date
    return datetime.fromtimestamp(0)

#Helpers [Async]
async def UpdateMessageDB(Database: sqlite3.Connection, App:Client, CHAT: Chat, LASTUPDATE: datetime):
    _cursor = Database.cursor()

    async for _m in App.get_chat_history(CHAT.id):
        if not _m.media:
            continue

        _dres = _cursor.execute(f"""
        SELECT id
        FROM messages
        WHERE id = {_m.id}
        AND chat_id = {CHAT.id}
        """)

        if not _dres.fetchone() is None:
            break
        else:
            _ = _cursor.execute(f"""
            INSERT INTO messages(
                id,
                chat_id,
                size,
                complete
            )
            VALUES(
                {_m.id},
                {CHAT.id},
                {MessageMediaSize(_m)},
                FALSE
            )
            """)
    _ = _cursor.execute(f"""
    UPDATE chats
    SET
        last_update = '{LASTUPDATE.isoformat()}'
    WHERE id = {CHAT.id}
    """)
    Database.commit()

def CreateAsyncProgressBar (Background: int, Foreground: int, Text: int):
    pbcb = CreateProgressBar(Background, Foreground, Text)

    async def callback (current: int, total: int):
        return pbcb(current / total)

    return callback

def LoadConfig (path: str):
    config: dict[str, Any] = {}
    with open(path) as f:
        try:
            config = json.load(f)
        except json.JSONDecodeError:
            return None
    return config

CONFIG_PATH = "./config.json"
DB_PATH = "./TeleDown.db"

#Main Function
async def DownloadMain(App: Client, Database: sqlite3.Connection, CHAT_ID: int, DLDIR: str, Order: str = "id ASC"):
    async with App:
        #Async Initilization
        _chat = await App.get_chat(CHAT_ID)
        CHAT = NarrowType(_chat, Chat(id = 0, type = ChatType.CHANNEL))
        LASTUPDATE = await GetLastUpdateTime(App, CHAT)
        db = Database.cursor()

        #Ensure Chat exists in Database
        _dres = db.execute(f"""
        SELECT id
        FROM chats
        WHERE id = {CHAT.id}
        """)
        if _dres.fetchone() is None:
            _ = db.execute(f"""
            INSERT INTO chats(id, last_update)
            VALUES(
                {CHAT.id},
                '{datetime.fromtimestamp(0).isoformat()}'
            )
            """)
            Database.commit()
        _dres = db.execute(f"""
        SELECT last_update
        FROM chats
        WHERE id = {CHAT.id}
        """)
        db_update = datetime.fromisoformat(_dres.fetchone()[0])
        if LASTUPDATE > db_update:
            await UpdateMessageDB(Database, App, CHAT, LASTUPDATE)
        Database = IndexDirectory(DLDIR, Database)
        UpdateFileDB(Database)
        _dres = db.execute(f"""
        SELECT id 
        FROM messages
        WHERE complete = FALSE
        AND chat_id = {CHAT.id}
        ORDER BY {Order}
        """)
        new_messages: list[int] = [r[0] for r in _dres.fetchall()]
        for message_id in new_messages:

            _m = await App.get_messages(CHAT.id, message_id)
            message = NarrowType(_m, Message(id = 0))

            print(f"Starting {message.id}...")
            progress_bar = CreateAsyncProgressBar(18, 231, 251)
            _sp = await App.download_media(message, DLDIR, progress = progress_bar)

            if _sp is None:
                print(f"Failed to download {message.id}. Exiting...")
                break
            saved_path = str(_sp)
            saved_size = Path(saved_path).stat().st_size

            if saved_size < MessageMediaSize(message):
                print(f"Failed to download {saved_path}. Exiting...")
                break

            _ = db.execute(f"""
            UPDATE messages
            SET
                complete = TRUE,
                file = '{saved_path}'
            WHERE id = {message.id}
            AND chat_id = {CHAT.id}
            """)
            Database.commit()
            print("Press X in 5 seconds to cancel further downloads...")
            if TimedPromptKey(5, 'x'):
                break
    return None

#Main Initialization
if __name__ == "__main__":
    #Sync Initialization
    if not Path(CONFIG_PATH).exists():
        print(f"Configuration file [{CONFIG_PATH}] does not exist")
        exit(-1)
    CONFIG = LoadConfig(CONFIG_PATH)
    if CONFIG is None:
        print(f"Failed to load configuration from file {CONFIG_PATH}")
        exit(-1)

    CHAT_ID = int(CONFIG["CHAT_ID"])
    if not Path(CONFIG["DLDIR"]).exists():
        print(f"Download destination {CONFIG["DLDIR"]} does not exist")
        exit(-1)
    DLDIR = str(CONFIG["DLDIR"])

    Order = "id ASC"
    if CONFIG["Order"]:
        Order = str(CONFIG["Order"])

    API_ID = str(CONFIG["ApiID"])
    API_HASH = str(CONFIG["ApiHash"])

    Database = DBInit(DB_PATH)

    App = Client("TeleDown", api_id = API_ID, api_hash = API_HASH, app_version = "0.0.1b")

    #Run Main
    App.run(DownloadMain(App, Database, CHAT_ID, DLDIR, Order))

    #Cleanup
    Database.close()
