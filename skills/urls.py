from django.urls import path
from . import views

app_name = 'skills'

urlpatterns = [
    path('', views.browse_skills, name='browse'),
    path('my-lessons/', views.my_lessons, name='my_lessons'),
    path('<slug:slug>/', views.skill_detail, name='detail'),
    path('<slug:slug>/lesson/<int:order>/', views.lesson_detail, name='lesson'),
    path('<slug:slug>/learned/', views.mark_as_learned, name='mark_learned'),
    path('<slug:slug>/add-lesson/', views.add_lesson, name='add_lesson'),
    path('<slug:slug>/lesson/<int:order>/helpful/', views.vote_lesson_helpful, name='vote_helpful'),
    path('<slug:slug>/lesson/<int:order>/report/', views.report_lesson, name='report_lesson'),
]