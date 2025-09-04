from django.urls import path
from .views import HealthView, PredictView, ModelsView, RecordsView, MetricsOverviewView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("predict", PredictView.as_view(), name="predict"),
    path("models", ModelsView.as_view(), name="models"),
    path("records", RecordsView.as_view(), name="records"),
    path("metrics/overview", MetricsOverviewView.as_view(), name="metrics-overview"),
]
