from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F
from django.contrib.auth.models import User
from .models import Proyeccion, InventarioItem, ClimaDiario, Especie, Perfil, Lote, Zona, Pedido, PedidoDetalle, Alerta, ReservaInventario
from datetime import date, timedelta, datetime
from decimal import Decimal
from django.utils import timezone
from .services import calcular_media_historica_7_dias, calcular_factor_proyeccion_14_dias 
import requests

# --- Configuración de API (CRÍTICO: Mover a settings.py en producción) ---
API_KEY = '74dfedb7d8d15688e1502c5cab863b7' # Clave activa
CIUDAD = 'Caldera,CL'
URL_CLIMA = f'http://api.openweathermap.org/data/2.5/weather?q={CIUDAD}&appid={API_KEY}&units=metric'

def rol_requerido(rol):
    def decorator(view_func):
        def wrapper_func(request, *args, **kwargs):
            if request.user.is_authenticated:
                try:
                    # Permite acceso al rol específico O al superusuario
                    if request.user.perfil.rol == rol or request.user.is_superuser:
                        return view_func(request, *args, **kwargs)
                except Perfil.DoesNotExist:
                    pass
            # Redirige a acceso denegado si no cumple el rol
            return render(request, 'acceso_denegado.html', status=403) 
        return wrapper_func
    return decorator

# 1. Función para el Dashboard
@login_required 
def dashboard(request):
    return render(request, 'dashboard.html', {})

# 2. Función para registrar la biomasa (Coordinador de Cultivo)
@rol_requerido('CULTIVO') 
def registro_biomasa(request):
    especies = Especie.objects.all()
    zonas = Zona.objects.all()
    
    if request.method == 'POST':
        # --- Lógica de Procesamiento y Guardado (MVP) ---
        especie_id = request.POST.get('especie')
        zona_id = request.POST.get('zona')
        peso_humedo = request.POST.get('peso_humedo')
        
        # 1. Crear el Lote
        nueva_especie = Especie.objects.get(pk=especie_id)
        nueva_zona = Zona.objects.get(pk=zona_id)
        
        nuevo_lote = Lote.objects.create(
            especie=nueva_especie,
            zona=nueva_zona,
            peso_humedo_inicial=peso_humedo,
        )
        
        # 2. Crear el InventarioItem VIVO asociado al Lote (Inventario Vivo)
        InventarioItem.objects.create(
            lote=nuevo_lote,
            especie=nueva_especie,
            zona=nueva_zona,
            cantidad=peso_humedo, 
            estado='VIVO'
        )
        
        return redirect('dashboard') 
        
    return render(request, 'registro_biomasa.html', {'especies': especies, 'zonas': zonas})
    

# 3. Lógica de Proyección (Gerente de Planta)
@rol_requerido('PLANTA') 
def calcular_proyeccion(request):
    # 1. Obtener Inventario Vivo (MVP crítico)
    inventario_vivo = InventarioItem.objects.filter(estado='VIVO').values('especie').annotate(
        total_humedo=Sum('cantidad')
    )
    
    # 2. Obtener Datos Climáticos de Caldera (API METEOROLÓGICA)
    alerta_mensaje = "Proyección generada sin alertas." # Mensaje por defecto

    try:
        response = requests.get(URL_CLIMA)
        response.raise_for_status() 
        datos_clima = response.json()
        
        humedad_actual = datos_clima['main']['humidity'] 
        condicion_clima = datos_clima['weather'][0]['description']
        
        # 3. Guardar o Usar el Clima de Hoy (para evitar el error UNIQUE constraint)
        registro_clima_hoy, created = ClimaDiario.objects.get_or_create(
            fecha=timezone.localdate(),
            defaults={
                'humedad': f"{humedad_actual}%",
                'radiacion_solar': "ND (Vía API)",
                'condicion': condicion_clima
            }
        )
        
        # 4. Aplicar Alerta Climática (Gestión de la Incertidumbre)
        # Esto solo genera el mensaje, la lógica predictiva está en services.py
        if humedad_actual > 80:
            alerta_mensaje = f"Alerta Crítica: Humedad en Caldera ({humedad_actual}%) reducirá capacidad."
        elif humedad_actual > 60:
            alerta_mensaje = f"Advertencia: Humedad en Caldera ({humedad_actual}%) afectará ligeramente la proyección."

    except requests.exceptions.RequestException as e:
        alerta_mensaje = f"Error: No se pudo conectar a la API. Usando modelo predictivo histórico. {e}"

    proyecciones = []

    # 5. Iterar sobre el inventario y generar las proyecciones usando el modelo interno
    for item in inventario_vivo:
        especie = Especie.objects.get(pk=item['especie'])
        
        # *** MODELO PREDICTIVO INTERNO (services.py) ***
        
        # 5a. Calcular el rendimiento promedio de 7 días basado en historial (Modelo Interno)
        capacidad_7_dias_historica = calcular_media_historica_7_dias(especie.id)
        
        # 5b. Si no hay historial, se usa la capacidad seca base como respaldo (BACKUP)
        if capacidad_7_dias_historica == Decimal('0.0'):
            # Usamos la conversión 6:1 del inventario VIVO como BACKUP
            capacidad_seca_base = item['total_humedo'] / especie.factor_conversion
            capacidad_7_dias = capacidad_seca_base * Decimal('0.50') 
            alerta_mensaje = "Advertencia: Proyección basada en el inventario actual (sin historial)."
        else:
            # Usamos el resultado del modelo predictivo (media histórica ponderada)
            capacidad_7_dias = capacidad_7_dias_historica
            
        # Proyección a 7 días (Guardar resultado del Modelo Interno)
        Proyeccion.objects.create(
            especie=especie, dias=7, capacidad_estimada=capacidad_7_dias
        )
        
        # 5c. Proyección a 14 días (Modelo Interno basado en factor de 7 días)
        capacidad_14_dias = calcular_factor_proyeccion_14_dias(capacidad_7_dias)
        Proyeccion.objects.create(
            especie=especie, dias=14, capacidad_estimada=capacidad_14_dias
        )

        proyecciones.append({
            'especie': especie.nombre_especie,
            '7_dias': f"{capacidad_7_dias:.2f} kg secos",
            '14_dias': f"{capacidad_14_dias:.2f} kg secos",
        })

    return render(request, 'proyeccion_resultado.html', {
        'proyecciones': proyecciones, 
        'success': True,
        'alerta_clima': alerta_mensaje # Muestra el mensaje climático en el resultado
    })


# 4. Lógica de Pedido (Ejecutivo Comercial)
@rol_requerido('COMERCIAL') 
def registro_pedido(request):
    especies = Especie.objects.all()
    mensaje = None
    color = None
    
    if request.method == 'POST':
        # 1. Capturar datos del POST
        fecha_entrega_str = request.POST.get('fecha_entrega')
        especie_id = request.POST.get('especie')
        volumen_seco = Decimal(request.POST.get('volumen_seco'))
        granulometria = request.POST.get('granulometria')

        fecha_entrega = datetime.strptime(fecha_entrega_str, '%Y-%m-%d').date()
        hoy = timezone.localdate()
        diferencia_dias = (fecha_entrega - hoy).days
        
        # --- Lógica de Verificación de Factibilidad ---
        
        # a) Consultar TODO el Inventario (Vivo y Seco)
        inventario_total_humedo = InventarioItem.objects.filter(
            especie_id=especie_id
        ).aggregate(total_sum=Sum('cantidad'))['total_sum'] or Decimal('0.0')
        
        especie_obj = Especie.objects.get(pk=especie_id)
        factor = especie_obj.factor_conversion
        
        capacidad_total_seco_base = inventario_total_humedo / factor # Conversión 6:1
        capacidad_total = capacidad_total_seco_base
        
        # b) Consultar Proyección
        proyeccion = Proyeccion.objects.filter(
            especie_id=especie_id,
            dias__gte=diferencia_dias 
        ).order_by('dias').first() 

        if proyeccion:
            capacidad_total += proyeccion.capacidad_estimada

        # c) Decisión: ¿La capacidad es mayor al producto? (Trazabilidad y Riesgo)
        if capacidad_total >= volumen_seco:
            estado_pedido = 'FACTIBLE'
            mensaje = f"✅ Pedido Factible. Capacidad total estimada: {capacidad_total:.2f} kg secos."
            color = 'green'
            
            # LÓGICA DE TRAZABILIDAD Y RESERVA
            nuevo_pedido = Pedido.objects.create(
                usuario=request.user, fecha_entrega=fecha_entrega, estado=estado_pedido
            )
            detalle = PedidoDetalle.objects.create(
                pedido=nuevo_pedido, especie_id=especie_id, volumen_en_seco=volumen_seco,
                granulometria=granulometria, estado=estado_pedido
            )
            
            inventario_item = InventarioItem.objects.filter(especie_id=especie_id).latest('fecha_actualizacion') 
            ReservaInventario.objects.create(
                pedidodetalle=detalle, inventarioitem=inventario_item,
                cantidad_reservada=volumen_seco, estado_reserva='RESERVADO'
            )

        else: # (capacidad_total < volumen_seco)
            estado_pedido = 'RIESGO'
            mensaje = f"⚠️ Pedido en RIESGO (Incumplimiento). Capacidad disponible: {capacidad_total:.2f} kg secos. Faltan: {(volumen_seco - capacidad_total):.2f} kg."
            color = 'red'
            
            # LÓGICA DE ALERTA CRÍTICA (TC-40)
            nuevo_pedido = Pedido.objects.create(
                usuario=request.user, fecha_entrega=fecha_entrega, estado=estado_pedido
            )
            detalle = PedidoDetalle.objects.create(
                pedido=nuevo_pedido, especie_id=especie_id, volumen_en_seco=volumen_seco,
                granulometria=granulometria, estado=estado_pedido
            )
            
            usuario_admin = User.objects.get(pk=1) 
            Alerta.objects.create(
                usuario=usuario_admin, tipo='INCUMPLIMIENTO OTD',
                mensaje=f"Riesgo: Pedido {nuevo_pedido.id} supera la capacidad en {(volumen_seco - capacidad_total):.2f} kg. Fecha: {fecha_entrega_str}",
                nivel='CRITICA', en_mail=False 
            )

    return render(request, 'registro_pedido.html', {
        'especies': especies, 
        'mensaje': mensaje, 
        'color': color
    })