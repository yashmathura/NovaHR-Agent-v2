from django.urls import path
from .views import chat_page, chat_api
urlpatterns=[path("",chat_page,name="agent_chat"),path("api/",chat_api,name="agent_api")]
