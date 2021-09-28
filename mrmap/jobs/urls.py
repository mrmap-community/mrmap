from django.urls import path, include
from jobs import views

app_name = 'jobs'
urlpatterns = [
    path('jobs', views.JobListView.as_view(), name="job_list"),
    path('tasks', views.TaskListView.as_view(), name="task_list"),
]

