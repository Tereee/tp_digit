import base64, io, time, pickle, tempfile, os
import numpy as np
from PIL import Image, ImageOps

_tf = None

from .storage import get_db, load_binary

_model_cache = None  # {"model": obj, "meta": {...}}

def _ensure_tf():
    global _tf
    if _tf is None:
        import tensorflow as tf
        _tf = tf
    return _tf

def _decode_dataurl_to_pil(data_url: str) -> Image.Image:
    header, b64 = data_url.split(',', 1)
    img_bytes = base64.b64decode(b64)
    img = Image.open(io.BytesIO(img_bytes))
    return img.convert("L") 

def _to_28x28(img: Image.Image) -> Image.Image:
    if np.mean(np.array(img)) > 127:
        img = ImageOps.invert(img)
    img = img.resize((28, 28), Image.Resampling.LANCZOS)
    return img

def _prep_sklearn(img: Image.Image) -> np.ndarray:
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return arr.reshape(1, 28*28)

def _prep_keras(img: Image.Image) -> np.ndarray:
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return arr.reshape(1, 28, 28, 1)

def _load_default_model_from_db():
    """Charge le modèle is_default=true depuis Mongo (GridFS)."""
    db = get_db()
    m = db.models.find_one({"is_default": True})
    if not m or not m.get("gridfs_id"):
        return None
    fmt = m.get("format", "pickle").lower()
    raw = load_binary(m["gridfs_id"])

    if fmt == "pickle":
        model = pickle.loads(raw)
    elif fmt in ("h5", "keras"):
        tf = _ensure_tf()
        suffix = ".h5" if fmt == "h5" else ".keras"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(raw)
            tmp_path = f.name
        try:
            model = tf.keras.models.load_model(tmp_path)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    else:
        raise ValueError(f"Format modèle non supporté: {fmt}")

    return {"model": model, "meta": {"_id": m["_id"], "algo": m.get("algo"), "format": fmt}}

def _ensure_model_loaded():
    global _model_cache
    if _model_cache is None:
        _model_cache = _load_default_model_from_db()
    return _model_cache

def clear_model_cache():
    global _model_cache
    _model_cache = None

def predict_from_dataurl(data_url: str):
    """Retourne: digit, proba, using_model(bool), latency_ms"""
    t0 = time.perf_counter()
    try:
        holder = _ensure_model_loaded()
        img = _decode_dataurl_to_pil(data_url)
        img28 = _to_28x28(img)

        if holder is None:
            return 7, 0.99, False, int((time.perf_counter()-t0)*1000)

        model = holder["model"]
        fmt = holder["meta"]["format"]

        if fmt == "pickle":
            X = _prep_sklearn(img28)
            if hasattr(model, "predict_proba"):
                proba_vec = model.predict_proba(X)[0]
                pred = int(np.argmax(proba_vec))
                proba = float(np.max(proba_vec))
            else:
                pred = int(model.predict(X)[0])
                proba = 0.0
        else:
            _ = _ensure_tf()
            X = _prep_keras(img28)
            proba_vec = model.predict(X, verbose=0)[0]
            pred = int(np.argmax(proba_vec))
            proba = float(np.max(proba_vec))

        latency_ms = int((time.perf_counter()-t0)*1000)
        return pred, proba, True, latency_ms
    except Exception:
        latency_ms = int((time.perf_counter()-t0)*1000)
        return 7, 0.99, False, latency_ms
