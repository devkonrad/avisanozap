from django.contrib import admin

from .models import (
    AsaasWebhookEvent,
    BillingSettings,
    BillingPlan,
    MercadoPagoWebhookEvent,
    Payment,
    Subscription,
)

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'professional',
        'plan',
        'status',
        'amount',
        'provider',
        'started_at',
        'expires_at',
    )
    list_filter = ('plan', 'status', 'provider')
    search_fields = (
        'professional__user__username',
        'provider_customer_id',
        'provider_subscription_id',
        'provider_checkout_id',
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'subscription',
        'amount',
        'status',
        'provider',
        'due_date',
        'paid_at',
    )
    list_filter = ('status', 'provider')
    search_fields = ('provider_payment_id',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BillingSettings)
class BillingSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'checkout_provider',
        'reminder_business_days',
    )

    def has_add_permission(self, request):
        if BillingSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AsaasWebhookEvent)
class AsaasWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        'event_id',
        'event_type',
        'status',
        'received_at',
        'processed_at',
    )
    list_filter = ('status', 'event_type')
    search_fields = ('event_id', 'event_type')
    readonly_fields = (
        'event_id',
        'event_type',
        'payload',
        'status',
        'received_at',
        'processed_at',
        'error_message',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BillingPlan)
class BillingPlanAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'amount',
        'billing_type',
        'payment_method',
        'access_days',
        'is_active',
        'sort_order',
    )
    list_filter = ('billing_type', 'payment_method', 'is_active')
    search_fields = ('code', 'name', 'description')
    list_editable = ('amount', 'is_active', 'sort_order')
    ordering = ('sort_order', 'name')
    readonly_fields = ('created_at', 'updated_at')
    prepopulated_fields = {'code': ('name',)}


@admin.register(MercadoPagoWebhookEvent)
class MercadoPagoWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        'event_id',
        'event_type',
        'status',
        'received_at',
        'processed_at',
    )
    list_filter = ('status', 'event_type')
    search_fields = ('event_id', 'event_type')
    readonly_fields = (
        'event_id',
        'event_type',
        'payload',
        'status',
        'received_at',
        'processed_at',
        'error_message',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
