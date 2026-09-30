from django.contrib import admin
from .models import CreditWallet, CreditTransaction


@admin.register(CreditWallet)
class CreditWalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'total_earned', 'total_spent', 'updated_at')
    search_fields = ('user__username', 'user__email')


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'amount', 'transaction_type', 'created_at')
    list_filter = ('transaction_type',)
    search_fields = ('wallet__user__username', 'description')