from django.urls import path

from .ask import AskView

urlpatterns = [path("ask/", AskView.as_view(), name="ask")]
