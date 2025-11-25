from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F
from .models import Proyeccion, InventarioItem, ClimaDiario, Especie, Perfil, Lote, Zona, Pedido, PedidoDetalle, Alerta, ReservaInventario, User
from datetime import date, timedelta, datetime
from decimal import Decimal
from django.utils import timezone



def rol_requerido(rol):
    def decorator(view_func):
        def wrapper_func(request, *args, **kwargs):
            if request.user.is_authenticated:
                try:
                    if request.user.perfil.rol == rol or request.user.is_superuser:
                        return view_func(request, *args, **kwargs)
                except Perfil.DoesNotExist:
                    pass
            return render(request, 'acceso_denegado.html', status=403) 
        return wrapper_func
    return decorator

# 1. Función para el Dashboard
@login_required 
def dashboard(request):
    return render(request, 'dashboard.html', {})

# 2. Función para registrar la biomasa
@login_required
def registro_biomasa(request):
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
            # peso_seco_final se deja nulo hasta que se procese
        )
        
        # 2. Crear el InventarioItem VIVO asociado al Lote (El Inventario Vivo es un MVP crítico) [cite: 63]
        InventarioItem.objects.create(
            lote=nuevo_lote,
            especie=nueva_especie,
            zona=nueva_zona,
            cantidad=peso_humedo, 
            estado='VIVO'
        )
        
        return redirect('dashboard') 
        
    else:
        # --- Lógica para mostrar el formulario ---
        especies = Especie.objects.all()
        zonas = Zona.objects.all()
        return render(request, 'registro_biomasa.html', {'especies': especies, 'zonas': zonas})
    

# Lógica de Proyección - CRÍTICA para el Gerente de Planta
# Implementando RBAC: Solo Gerente de Planta (PLANTA) o Admin pueden ejecutar
@rol_requerido('PLANTA') 
def calcular_proyeccion(request):
    # 1. Obtener Inventario Vivo (MVP crítico)
    inventario_vivo = InventarioItem.objects.filter(estado='VIVO').values('especie').annotate(
        total_humedo=Sum('cantidad')
    )
    
    proyecciones = []
    
    for item in inventario_vivo:
        especie = Especie.objects.get(pk=item['especie'])
        total_humedo = item['total_humedo']
        factor = especie.factor_conversion # 6:1 (ej. 6.00)
        
        # 2. Aplicar la compleja conversión 6:1 (Húmedo a Seco) [cite: 52, 125]
        capacidad_seca_base = total_humedo / factor

        # 3. Considerar impacto climático (Simplificación para MVP)
        # Se asume que el clima futuro ideal nos permite procesar el 100%
        # En una versión avanzada, se usaría ClimaDiario para modular esto.
        
        # 4. Generar Proyección a 7 y 14 días
        
        # Proyección a 7 días (ej. procesar el 50% de la capacidad seca base)
        capacidad_7_dias = capacidad_seca_base * Decimal(0.50)
        Proyeccion.objects.create(
            especie=especie, 
            dias=7, 
            capacidad_estimada=capacidad_7_dias
        )

        # Proyección a 14 días (ej. procesar el 80% de la capacidad seca base)
        capacidad_14_dias = capacidad_seca_base * Decimal(0.80)
        Proyeccion.objects.create(
            especie=especie, 
            dias=14, 
            capacidad_estimada=capacidad_14_dias
        )

        proyecciones.append({
            'especie': especie.nombre_especie,
            '7_dias': f"{capacidad_7_dias:.2f} kg secos",
            '14_dias': f"{capacidad_14_dias:.2f} kg secos",
        })

    return render(request, 'proyeccion_resultado.html', {'proyecciones': proyecciones, 'success': True})


@rol_requerido('COMERCIAL') 
def registro_pedido(request):
    especies = Especie.objects.all()
    
    # Inicializar variables a None para evitar NameError si el formulario no se postea
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
        
        # Obtenemos el factor de conversión CRÍTICO (ej. 6.00)
        especie_obj = Especie.objects.get(pk=especie_id)
        factor = especie_obj.factor_conversion
        
        # Aplicar la compleja conversión 6:1 (Inventario Húmedo Total a Capacidad Seca Base)
        capacidad_total_seco_base = inventario_total_humedo / factor

        capacidad_total = capacidad_total_seco_base
        
        # b) Consultar Proyección
        proyeccion = Proyeccion.objects.filter(
            especie_id=especie_id,
            dias__gte=diferencia_dias 
        ).order_by('dias').first() 

        if proyeccion:
            capacidad_total += proyeccion.capacidad_estimada

        # c) Decisión: ¿La capacidad es mayor al producto? 
        if capacidad_total >= volumen_seco:
            estado_pedido = 'FACTIBLE'
            mensaje = f"✅ Pedido Factible. Capacidad total estimada: {capacidad_total:.2f} kg secos."
            color = 'green'
            
            # 1. Registrar el Pedido (con estado FACTIBLE)
            nuevo_pedido = Pedido.objects.create(
                usuario=request.user, 
                fecha_entrega=fecha_entrega,
                estado=estado_pedido
            )
            detalle = PedidoDetalle.objects.create(
                pedido=nuevo_pedido,
                especie_id=especie_id,
                volumen_en_seco=volumen_seco,
                granulometria=granulometria,
                estado=estado_pedido
            )
            
            # 2. Crear el registro de RESERVA de Inventario (Trazabilidad)
            inventario_item = InventarioItem.objects.filter(especie_id=especie_id).latest('fecha_actualizacion') 

            ReservaInventario.objects.create(
                pedidodetalle=detalle,
                inventarioitem=inventario_item,
                cantidad_reservada=volumen_seco, 
                estado_reserva='RESERVADO'
            )

        else: # (capacidad_total < volumen_seco)
            estado_pedido = 'RIESGO'
            mensaje = f"⚠️ Pedido en RIESGO (Incumplimiento). Capacidad disponible: {capacidad_total:.2f} kg secos. Faltan: {(volumen_seco - capacidad_total):.2f} kg."
            color = 'red'
            
            # 1. Registrar el Pedido (con estado RIESGO)
            nuevo_pedido = Pedido.objects.create(
                usuario=request.user, 
                fecha_entrega=fecha_entrega,
                estado=estado_pedido
            )
            detalle = PedidoDetalle.objects.create(
                pedido=nuevo_pedido,
                especie_id=especie_id,
                volumen_en_seco=volumen_seco,
                granulometria=granulometria,
                estado=estado_pedido
            )
            
            # 2. Generar Alerta Crítica (TC-40)
            usuario_admin = User.objects.get(pk=1) 

            Alerta.objects.create(
                usuario=usuario_admin,
                tipo='INCUMPLIMIENTO OTD',
                mensaje=f"Riesgo: Pedido {nuevo_pedido.id} supera la capacidad en {(volumen_seco - capacidad_total):.2f} kg. Fecha: {fecha_entrega_str}",
                nivel='CRITICA',
                en_mail=False 
            )

    return render(request, 'registro_pedido.html', {
        'especies': especies, 
        'mensaje': mensaje, 
        'color': color
    })