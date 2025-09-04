import os
from django.conf import settings
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from gridfs import GridFS

_client = None
_db = None
_fs = None

def get_client():
    global _client
    if _client is None:
        uri = getattr(settings, "MONGO_URI", None) or os.getenv("MONGO_URI")
        if not uri:
            raise RuntimeError("MONGO_URI manquant. Définis-le dans .env")
        _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    return _client

def get_db():
    global _db
    if _db is None:
        db_name = getattr(settings, "MONGO_DB", None) or os.getenv("MONGO_DB", "mnist_app")
        _db = get_client()[db_name]
    return _db

def get_fs():
    global _fs
    if _fs is None:
        _fs = GridFS(get_db())
    return _fs

def ping():
    try:
        get_client().admin.command("ping")
        return True, None
    except PyMongoError as e:
        return False, str(e)

def save_binary_bytes(data_bytes, filename: str, content_type: str | None = None):
    fs = get_fs()
    return fs.put(data_bytes, filename=filename, content_type=content_type)

def load_binary(gridfs_id):
    fs = get_fs()
    gridout = fs.get(gridfs_id)
    return gridout.read()
