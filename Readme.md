# Backend MNIST — Django REST + TensorFlow + MongoDB Atlas

Backend d’inférence de chiffres manuscrits (type MNIST). Le front envoie une image en **dataURL (PNG base64)**, le backend la prétraite au format MNIST (28×28×1) et prédit la classe **0–9** via un modèle **Keras/TensorFlow** stocké dans **MongoDB Atlas (GridFS)**.

---

## Sommaire
- [Stack & Architecture](#stack--architecture)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration (.env)](#configuration-env)
- [Lancer en local](#lancer-en-local)
- [Vérifications rapides](#vérifications-rapides)
- [Référence d’API](#référence-dapi)
  - [/api/v1/health](#get-apiv1health)
  - [/api/v1/models](#models-gestion-de-modèles)
  - [/api/v1/predict](#post-apiv1predict)
  - [/api/v1/records](#get-apiv1records)
  - [/api/v1/metrics/overview](#get-apiv1metricsoverview)
- [Données MongoDB (schémas)](#données-mongodb-schémas)
- [Détails de prétraitement image](#détails-de-prétraitement-image)
- [Dépannage](#dépannage)
- [Notes déploiement / prod](#notes-déploiement--prod)

---

## Stack & Architecture
- **Framework** : Django 5 + Django REST Framework
- **ML** : TensorFlow/Keras (modèles **.h5** ou **.keras**)
- **Base de données** : MongoDB Atlas (GridFS pour les binaires de modèle)
- **Stockage modèle** : `models` (métadonnées) + `fs.files`/`fs.chunks` (binaire GridFS)
- **CORS** : `django-cors-headers` (ouvert en dev)

Flux:
1. Le front dessine un chiffre sur un `<canvas>` et envoie un **dataURL** PNG à `/api/v1/predict`.
2. Le backend **décode**, **prétraite** en 28×28×1, charge le **modèle par défaut** depuis Atlas (GridFS), **prédit**, logge en Mongo, renvoie JSON.

---

## Prérequis
- **Python 3.11**
- Accès à un **cluster MongoDB Atlas** (M0 gratuit OK) avec :
  - 1 utilisateur Read/Write
  - IP autorisée (ou `0.0.0.0/0` en dev)
  - Un modèle `.h5` uploadé et marqué `is_default: true` (voir section [models](#models-gestion-de-modèles))

---

## Installation

```bash
# Cloner
git clone <votre-repo>.git
cd mnist-backend

# Environnement virtuel (Windows)
py -3.11 -m venv .venv
.\.venv\Scripts\Activate

# Environnement virtuel (macOS/Linux)
# python3.11 -m venv .venv
# source .venv/bin/activate

# Dépendances
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**requirements.txt (exemple)**
```txt
Django>=5,<6
djangorestframework
django-cors-headers
pillow
numpy
pymongo
python-dotenv
h5py
tensorflow>=2.16,<2.18
```

---

## Configuration (.env)
Créez un fichier `.env` à la racine :
```ini
MONGO_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGO_DB=mnist_app
```

> `MONGO_URI` doit pointer vers le **même cluster** que celui contenant votre modèle (GridFS). Assurez-vous que l’IP locale est autorisée dans Atlas (Network Access).

Optionnel (debug local sans Atlas) – non utilisé par défaut :
```ini
# MODEL_LOCAL_PATH=C:\chemin\vers\modele_local.h5
```

---

## Lancer en local
```bash
python manage.py runserver
```

---

## Vérifications rapides
- **Health** : <http://127.0.0.1:8000/api/v1/health>
  - Attendu : `{ "status": "ok", "mongo": "connected" }`
- **Modèles** : <http://127.0.0.1:8000/api/v1/models>
  - Attendu : au moins un modèle avec `is_default: true` et `has_binary: true`
- **Prédiction** (exemple avec une image locale transformée en dataURL)

PowerShell :
```powershell
$bytes = [IO.File]::ReadAllBytes("C:\\chemin\\vers\\mon_chiffre.png")
$b64   = [Convert]::ToBase64String($bytes)
$img   = "data:image/png;base64,$b64"
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/predict -ContentType 'application/json' -Body (@{ image = $img } | ConvertTo-Json)
```

Python :
```python
import base64, requests
with open('mon_chiffre.png', 'rb') as f:
    b64 = base64.b64encode(f.read()).decode('ascii')
img = f'data:image/png;base64,{b64}'
r = requests.post('http://127.0.0.1:8000/api/v1/predict', json={'image': img})
print(r.json())
```

---

## Référence d’API

### GET `/api/v1/health`
Retourne l’état de l’application et la connectivité MongoDB.

Exemple
```json
{ "status": "ok", "mongo": "connected" }
```

---

### `/models` — Gestion de modèles

#### GET `/api/v1/models`
Liste les modèles déclarés.

Exemple
```json
[
  {
    "id": "...",
    "name": "keras_mnist_prod",
    "algo": "Keras",
    "format": "h5",
    "metrics": {},
    "is_default": true,
    "created_at": "2025-09-03T23:24:01.215596",
    "has_binary": true
  }
]
```

#### POST `/api/v1/models` (multipart/form-data)
Crée un modèle. Si `is_default=true`, il devient le modèle par défaut (chargé au prochain `/predict`).

Champs
- `name` (texte) — requis
- `algo` (texte, ex. `Keras`) — requis
- `format` (`h5`|`keras`|`pickle`) — défaut : `h5`
- `is_default` (`true`|`false`) — optionnel
- `file` (binaire) — recommandé pour charger le modèle dans GridFS

Exemples d’upload
- **Windows (curl.exe, 1 ligne)**
```powershell
$path = "C:\\chemin\\modele.h5"
curl.exe -X POST "http://127.0.0.1:8000/api/v1/models" -F "name=keras_mnist_prod" -F "algo=Keras" -F "format=h5" -F "is_default=true" -F "file=@$path;type=application/octet-stream"
```
- **Postman** : Body → form-data → keys `name`, `algo`, `format`, `is_default`, `file` (type File)

Réponse (201)
```json
{
  "id": "...",
  "name": "keras_mnist_prod",
  "algo": "Keras",
  "format": "h5",
  "metrics": {},
  "is_default": true,
  "created_at": "...",
  "has_binary": true
}
```

> Remarque : changer de modèle par défaut sans réuploader peut être ajouté via un `PATCH /api/v1/models/{id}/default` (non inclus par défaut).

---

### POST `/api/v1/predict`
Prédit le chiffre à partir d’une image envoyée en **dataURL** (PNG base64).

Requête
```json
{
  "image": "data:image/png;base64,iVBORw0K...",
  "model_id": null
}
```

Réponse (200)
```json
{
  "id": "...",
  "digit": 3,
  "proba": 0.9769,
  "model_id": null,
  "latency_ms": 44,
  "using_model": true
}
```

Codes
- `400` si `image` est manquant ou invalide

---

### GET `/api/v1/records`
Retourne les dernières prédictions enregistrées.

Paramètres
- `limit` (int, défaut : 10)
- `only` (`correct`|`wrong`) — optionnel, actif si une ground truth a été annotée

Exemple
```json
[
  { "id": "...", "pred_digit": 7, "proba": 0.99, "created_at": "...", "model_id": null, "stub": false }
]
```

---

### GET `/api/v1/metrics/overview`
Statistiques simples côté prod.

Exemple
```json
{
  "total_records": 42,
  "predicted_distribution": [
    { "digit": 0, "count": 4 },
    { "digit": 1, "count": 8 },
    { "digit": 2, "count": 3 }
  ]
}
```

---

## Données MongoDB (schémas)

### `models`
```json
{
  "_id": ObjectId,
  "name": "keras_mnist_prod",
  "algo": "Keras",
  "format": "h5",
  "metrics": { "accuracy": 0.99 },
  "is_default": true,
  "gridfs_id": ObjectId,  // présent si fichier uploadé
  "created_at": ISODate("...")
}
```

### `drawings`
```json
{
  "_id": ObjectId,
  "image_type": "png_base64|gridfs",
  "image": "<base64>" | null,
  "pred_digit": 7,
  "proba": 0.99,
  "latency_ms": 12,
  "created_at": ISODate("..."),
  "model_id": null,
  "stub": false,
  "ground_truth": null
}
```

> GridFS : fichiers stockés dans `fs.files` / `fs.chunks`.

---

## Détails de prétraitement image
- Conversion **niveaux de gris (L)**
- Détection du fond via échantillons des coins ; inversion si fond clair
- Binarisation légère pour délimiter le tracé
- **Crop** au bounding box du tracé
- Mise à l’échelle pour que le plus grand côté = **20 px**
- **Centrage** sur canvas **28×28** par centre de masse
- Normalisation `[0,1]` et reshape `(1, 28, 28, 1)`

Ce pipeline améliore la robustesse par rapport à un simple `resize(28,28)`.

---

## Dépannage
- **`mongo": "error: ..."` dans `/health`**
  - Vérifier `MONGO_URI`, user/pass, IP autorisée dans Atlas.
- **`using_model: false` dans `/predict`**
  - Aucun modèle `is_default:true` en base, ou chargement Keras échoué.
  - Réuploader un `.h5` proprement via `/models`.
- **TensorFlow ne s’installe pas**
  - Vérifier Python **3.11** (Windows/macOS), mettre à jour `pip`.
- **CORS blocage depuis un front local**
  - Dev : `CORS_ALLOW_ALL_ORIGINS = True` (déjà actif). En prod, restreindre.

---

## Notes déploiement / prod
- Ajouter `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS` adaptés
- Restreindre CORS (`CORS_ALLOWED_ORIGINS`)
- Healthcheck `/api/v1/health`
- Serveur WSGI (gunicorn/uvicorn + Nginx) ou PaaS (Railway/Render)
- Variables d’env sécurisées (URI Atlas, etc.)
- Docker (exemple minimal) :

`Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

`docker-compose.yml`
```yaml
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MONGO_URI=${MONGO_URI}
      - MONGO_DB=${MONGO_DB}
```
