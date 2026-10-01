from django.urls import path
from . import views

app_name = 'skills'

urlpatterns = [
    path('', views.browse_skills, name='browse'),
    path('<slug:slug>/', views.skill_detail, name='detail'),
    path('<slug:slug>/lesson/<int:order>/', views.lesson_detail, name='lesson'),
    path('<slug:slug>/learned/', views.mark_as_learned, name='mark_learned'),
]