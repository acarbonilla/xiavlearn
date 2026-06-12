from django.urls import path
from .views import (
    health_check,
    ProfileView,
    SkillListView,
    CurriculumLevelListView,
    ModuleListView,
    ModuleDetailView,
    DashboardView,
)

urlpatterns = [
    path('health/', health_check, name='health-check'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('skills/', SkillListView.as_view(), name='skill-list'),
    path('levels/', CurriculumLevelListView.as_view(), name='curriculum-level-list'),
    path('modules/', ModuleListView.as_view(), name='module-list'),
    path('modules/<int:pk>/', ModuleDetailView.as_view(), name='module-detail'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
]
