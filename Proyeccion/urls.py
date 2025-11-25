# Proyeccion/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Dashboard (la vista principal del sistema)
    path('', views.dashboard, name='dashboard'),
    # Registro de Lotes (Coordinador de Cultivo)
    path('registro-biomasa/', views.registro_biomasa, name='registro_biomasa'),
    # Lógica de Proyección (Gerente de Planta)
    path('proyeccion-capacidad/', views.calcular_proyeccion, name='calcular_proyeccion'),
    # Nueva ruta para el Ejecutivo Comercial
    path('registro-pedido/', views.registro_pedido, name='registro_pedido'),
]