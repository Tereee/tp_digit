from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, JSONParser
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .storage import ping, get_db, save_binary_bytes
from .utils import oid_str, now_utc
from .inference import predict_from_dataurl, clear_model_cache

# --- Health ---
class HealthView(APIView):
    def get(self, request):
        ok, err = ping()
        return Response({
            "status": "ok" if ok else "degraded",
            "mongo": "connected" if ok else f"error: {err}"
        })

# --- /predict ---
@method_decorator(csrf_exempt, name="dispatch")
class PredictView(APIView):
    def post(self, request):
        data = request.data or {}
        image = data.get("image")
        model_id = data.get("model_id") 
        if not image or not isinstance(image, str) or not image.startswith("data:image"):
            return Response({"detail": "Champ 'image' (dataURL) requis"}, status=400)

        pred, proba, using_model, latency_ms = predict_from_dataurl(image)

        db = get_db()
        doc = {
            "image_type": "png_base64",
            "image": image if not using_model else None,
            "pred_digit": pred,
            "proba": proba,
            "latency_ms": latency_ms,
            "created_at": now_utc(),
            "model_id": model_id,
            "stub": not using_model
        }
        ins = db.drawings.insert_one(doc)
        return Response({
            "id": oid_str(ins.inserted_id),
            "digit": pred,
            "proba": proba,
            "model_id": model_id,
            "latency_ms": latency_ms,
            "using_model": using_model
        }, status=200)

# --- /models ---
class ModelsView(APIView):
    parser_classes = [MultiPartParser, JSONParser]

    def get(self, request):
        db = get_db()
        items = list(db.models.find().sort("created_at", -1))
        resp = []
        for m in items:
            resp.append({
                "id": oid_str(m.get("_id")),
                "name": m.get("name"),
                "algo": m.get("algo"),
                "format": m.get("format"),
                "metrics": m.get("metrics", {}),
                "is_default": bool(m.get("is_default", False)),
                "created_at": m.get("created_at"),
                "has_binary": bool(m.get("gridfs_id")) if "gridfs_id" in m else False
            })
        return Response(resp, status=200)

    def post(self, request):
        """
        Deux façons:
        - multipart/form-data avec 'file' (.h5/.keras ou pickle) + name, algo, format, is_default
        - application/json sans fichier (juste méta)
        """
        data = request.data or {}

        name = data.get("name")
        algo = data.get("algo")
        fmt = data.get("format", "h5") 
        is_default = str(data.get("is_default", "false")).lower() in ("1", "true", "yes")
        if not name or not algo:
            return Response({"detail": "Champs 'name' et 'algo' requis"}, status=400)

        gridfs_id = None
        upfile = request.FILES.get("file")
        if upfile:
            content = upfile.read()
            gridfs_id = save_binary_bytes(content, filename=upfile.name, content_type=upfile.content_type)

        db = get_db()
        if is_default:
            db.models.update_many({}, {"$set": {"is_default": False}})

        doc = {
            "name": name,
            "algo": algo,
            "format": fmt,
            "metrics": data.get("metrics", {}),
            "is_default": is_default,
            "created_at": now_utc()
        }
        if gridfs_id:
            doc["gridfs_id"] = gridfs_id

        ins = db.models.insert_one(doc)
        if is_default:
            clear_model_cache() 

        doc_out = {
            "id": oid_str(ins.inserted_id),
            "name": doc["name"],
            "algo": doc["algo"],
            "format": doc["format"],
            "metrics": doc.get("metrics", {}),
            "is_default": doc["is_default"],
            "created_at": doc["created_at"],
            "has_binary": bool(gridfs_id)
        }
        return Response(doc_out, status=201)

# --- /records ---
class RecordsView(APIView):
    def get(self, request):
        db = get_db()
        limit = int(request.query_params.get("limit", 10))
        only = request.query_params.get("only")
        query = {}
        if only in ("correct", "wrong"):
            query["ground_truth"] = {"$exists": True}
            if only == "correct":
                query["$expr"] = {"$eq": ["$ground_truth", "$pred_digit"]}
            else:
                query["$expr"] = {"$ne": ["$ground_truth", "$pred_digit"]}
        cursor = db.drawings.find(query).sort("created_at", -1).limit(limit)
        items = []
        for d in cursor:
            items.append({
                "id": oid_str(d.get("_id")),
                "pred_digit": d.get("pred_digit"),
                "proba": d.get("proba"),
                "created_at": d.get("created_at"),
                "model_id": d.get("model_id"),
                "stub": bool(d.get("stub", False)),
            })
        return Response(items, status=200)

# --- /metrics/overview ---
class MetricsOverviewView(APIView):
    def get(self, request):
        db = get_db()
        total = db.drawings.estimated_document_count()
        pipeline = [
            {"$group": {"_id": "$pred_digit", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        dist = list(db.drawings.aggregate(pipeline))
        distribution = [{"digit": d["_id"], "count": d["count"]} for d in dist if d["_id"] is not None]
        return Response({
            "total_records": total,
            "predicted_distribution": distribution
        }, status=200)
