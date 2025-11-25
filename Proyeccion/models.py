from django.db import models
from django.contrib.auth.models import User 



class Zona(models.Model):
    """Representa la zona o centro de cultivo submarino."""
    nombre_zona = models.CharField(max_length=45, verbose_name="Nombre de la Zona")
    ubicacion = models.CharField(max_length=45, verbose_name="Ubicación Geográfica")

    def __str__(self):
        return self.nombre_zona

class Especie(models.Model):
    """Representa las especies de alga (ej. Gracilaria, Macrocystis)."""
    nombre_especie = models.CharField(max_length=45, verbose_name="Nombre de la Especie")
    # Factor de conversión (6:1 húmedo a seco) - CRÍTICO para la Integridad (A08)
    factor_conversion = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Factor de Conversión (Húmedo:Seco)") 

    def __str__(self):
        return self.nombre_especie



class Lote(models.Model):
    """Registro de la biomasa recolectada o en proceso de secado."""
    especie = models.ForeignKey(Especie, on_delete=models.PROTECT) # Evita borrar la especie si hay lotes
    zona = models.ForeignKey(Zona, on_delete=models.PROTECT)       # Evita borrar la zona si hay lotes
    peso_humedo_inicial = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Peso Húmedo Inicial (kg)")
    peso_seco_final = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Peso Seco Final (kg)")
    fecha_registro = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"Lote {self.id} - {self.especie.nombre_especie}"

class InventarioItem(models.Model):
    """Inventario vivo disponible para la proyección."""
    ESTADOS = [
        ('VIVO', 'Vivo (en cultivo)'),
        ('SECO', 'Seco (terminado)'),
        ('PROCESO', 'En Proceso de Secado'),
    ]
    lote = models.ForeignKey(Lote, on_delete=models.PROTECT)
    especie = models.ForeignKey(Especie, on_delete=models.PROTECT)
    zona = models.ForeignKey(Zona, on_delete=models.PROTECT)
    cantidad = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cantidad Disponible (kg)")
    estado = models.CharField(max_length=45, choices=ESTADOS, default='VIVO')
    fecha_actualizacion = models.DateField(auto_now=True)

    def __str__(self):
        return f"Inventario {self.estado} de {self.cantidad} kg"



class ClimaDiario(models.Model):
    """Datos climáticos obtenidos de la API Meteorológica."""
    fecha = models.DateField(unique=True)
    humedad = models.CharField(max_length=45)
    radiacion_solar = models.CharField(max_length=45)
    condicion = models.CharField(max_length=45)

    def __str__(self):
        return f"Clima del {self.fecha}"

class Proyeccion(models.Model):
    """Resultado del cálculo de capacidad productiva a 7 o 14 días."""
    especie = models.ForeignKey(Especie, on_delete=models.PROTECT)
    dias = models.IntegerField(choices=[(7, '7 días'), (14, '14 días')])
    capacidad_estimada = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Capacidad Estimada (kg)")
    fecha_generacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Proyección a {self.dias} días para {self.especie}"



class Pedido(models.Model):
    """Registro de los pedidos de clientes (OTD)."""
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('FACTIBLE', 'Factible'),
        ('RIESGO', 'En Riesgo de Incumplimiento'),
        ('COMPLETADO', 'Completado'),
    ]
    # Usuario asociado al pedido (por ejemplo, el Ejecutivo Comercial)
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="Ejecutivo Comercial")
    fecha_entrega = models.DateField()
    estado = models.CharField(max_length=45, choices=ESTADOS, default='PENDIENTE')

    def __str__(self):
        return f"Pedido {self.id} - Estado: {self.estado}"

class PedidoDetalle(models.Model):
    """Detalle de lo que se pide en el pedido."""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE)
    especie = models.ForeignKey(Especie, on_delete=models.PROTECT)
    volumen_en_seco = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Volumen Seco Requerido (kg)")
    granulometria = models.CharField(max_length=45)
    estado = models.CharField(max_length=45, default='PENDIENTE')

    def __str__(self):
        return f"Detalle Pedido {self.pedido.id} - {self.volumen_en_seco} kg de {self.especie}"

class ReservaInventario(models.Model):
    """Asegura que el inventario está reservado para un pedido, clave para la Trazabilidad."""
    pedidodetalle = models.ForeignKey(PedidoDetalle, on_delete=models.CASCADE)
    inventarioitem = models.ForeignKey(InventarioItem, on_delete=models.PROTECT)
    cantidad_reservada = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cantidad Reservada (kg)")
    estado_reserva = models.CharField(max_length=45, default='RESERVADO')
    fecha_reserva = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"Reserva de {self.cantidad_reservada} kg para Pedido {self.pedidodetalle.pedido.id}"

class Alerta(models.Model):
    """Alertas de sistema (ej. riesgo de incumplimiento, clima adverso)."""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE) # Quién debe recibir la alerta
    tipo = models.CharField(max_length=45, verbose_name="Tipo de Alerta")
    mensaje = models.CharField(max_length=255)
    nivel = models.CharField(max_length=45, choices=[('CRITICA', 'Crítica'), ('ADVERTENCIA', 'Advertencia')])
    fecha = models.DateTimeField(auto_now_add=True)
    en_mail = models.BooleanField(default=False, verbose_name="Notificado por Email")

    def __str__(self):
        return f"Alerta {self.nivel}: {self.tipo}"
    
class Perfil(models.Model):
    """Extiende el modelo User de Django para añadir el Rol del SPCP-TR."""
    ROLES = [
        ('ADMIN', 'Administrador'),
        ('PLANTA', 'Gerente de Planta'),
        ('CULTIVO', 'Coordinador de Cultivo'),
        ('COMERCIAL', 'Ejecutivo Comercial'),
        ('AUDITOR', 'Auditor / Invitado'),
    ]


    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    rol = models.CharField(max_length=45, choices=ROLES, default='CULTIVO')

    def __str__(self):
        return f"Perfil de {self.usuario.username} ({self.get_rol_display()})"