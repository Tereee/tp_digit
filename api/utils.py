from datetime import datetime
from bson import ObjectId

def oid_str(oid):
    return str(oid) if isinstance(oid, ObjectId) else oid

def now_utc():
    return datetime.utcnow()
