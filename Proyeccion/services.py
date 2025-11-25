# Proyeccion/services.py
from django.db.models import Avg
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone
from .models import Proyeccion, Especie

def calcular_media_historica_7_dias(especie_id, dias_historial=30):
    """
    Modelo Predictivo Interno (MVP): Calcula la capacidad promedio de producción
    lograda para una especie en los últimos 'dias_historial'.
    Esto reemplaza la dependencia de una API de largo plazo.
    """
    try:
        # 1. Definir el período de historial (últimos 30 días)
        fecha_limite = timezone.localdate() - timedelta(days=dias_historial)
        
        # 2. Consultar las proyecciones pasadas de 7 días (capacidad real lograda)
        media_proyeccion = Proyeccion.objects.filter(
            especie_id=especie_id,
            dias=7, # Usamos la proyección de 7 días como indicador de rendimiento semanal
            fecha_generacion__date__gte=fecha_limite 
        ).aggregate(
            avg_capacidad=Avg('capacidad_estimada')
        )['avg_capacidad']
        
        # 3. Retornar la media o un valor seguro si no hay historial
        if media_proyeccion is not None:
            # Ponderar la media para la siguiente semana (ej. +5% de optimismo)
            return media_proyeccion * Decimal('1.05')
        else:
            # Si no hay historial, retornar un valor por defecto bajo para seguridad
            return Decimal('0.0') 
            
    except Exception as e:
        print(f"Error en el modelo predictivo: {e}")
        return Decimal('0.0')

def calcular_factor_proyeccion_14_dias(capacidad_7_dias):
    """
    Función que estima la proyección a 14 días basada en la proyección de 7 días.
    (Simple: asume un crecimiento lineal o factor fijo).
    """
    return capacidad_7_dias * Decimal('1.6') # Asume un aumento del 60% en la segunda semana