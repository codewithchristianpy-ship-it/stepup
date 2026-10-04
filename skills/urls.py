from django.urls import path
from . import views

app_name = 'skills'

urlpatterns = [
    path('', views.browse_skills, name='browse'),
    path('my-lessons/', views.my_lessons, name='my_lessons'),
    path('my-sessions/', views.my_sessions, name='my_sessions'),
    path('create-slot/', views.create_slot, name='create_slot'),

    # Session actions — before slug routes
    path('session/<int:session_id>/', views.session_detail, name='session_detail'),
    path('session/<int:session_id>/book/', views.book_slot, name='book_slot'),
    path('session/<int:session_id>/complete/', views.complete_session, name='complete_session'),
    path('session/<int:session_id>/cancel/', views.cancel_session, name='cancel_session'),
    path('session/<int:session_id>/feedback/', views.submit_feedback, name='submit_feedback'),

    path('<slug:slug>/', views.skill_detail, name='detail'),
    path('<slug:slug>/lesson/<int:order>/', views.lesson_detail, name='lesson'),
    path('<slug:slug>/learned/', views.mark_as_learned, name='mark_learned'),
    path('<slug:slug>/add-lesson/', views.add_lesson, name='add_lesson'),
    path('<slug:slug>/lesson/<int:order>/helpful/', views.vote_lesson_helpful, name='vote_helpful'),
    path('<slug:slug>/lesson/<int:order>/report/', views.report_lesson, name='report_lesson'),
]