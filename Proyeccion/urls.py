# Proyeccion/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('registro-biomasa/', views.registro_biomasa, name='registro_biomasa'),
    path('proyeccion-capacidad/', views.calcular_proyeccion, name='calcular_proyeccion'),
    path('registro-pedido/', views.registro_pedido, name='registro_pedido'),
]