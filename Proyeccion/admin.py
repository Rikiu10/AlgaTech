from django.contrib import admin
from .models import Zona, Especie, Lote, InventarioItem, ClimaDiario, Proyeccion, Pedido, PedidoDetalle, ReservaInventario, Alerta, Perfil


admin.site.register(Zona)

# Registrar modelo crítico con factor de conversión visible
@admin.register(Especie)
class EspecieAdmin(admin.ModelAdmin):
    list_display = ('nombre_especie', 'factor_conversion')


admin.site.register(Lote)
admin.site.register(ClimaDiario)
admin.site.register(Proyeccion)
admin.site.register(Alerta)


@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'rol')
    list_filter = ('rol',)
    # Los administradores son responsables de gestionar los roles

@admin.register(InventarioItem)
class InventarioItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'especie', 'zona', 'cantidad', 'estado', 'fecha_actualizacion')
    list_filter = ('estado', 'especie', 'zona')
    search_fields = ('especie__nombre_especie', 'zona__nombre_zona')