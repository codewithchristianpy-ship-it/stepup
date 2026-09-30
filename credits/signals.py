from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import CreditWallet, CreditTransaction


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_wallet(sender, instance, created, **kwargs):
    if created:
        wallet = CreditWallet.objects.create(user=instance, balance=3.00)
        CreditTransaction.objects.create(
            wallet=wallet,
            amount=3.00,
            transaction_type='signup_bonus',
            description='Welcome gift — 3 free credits to start learning',
        )