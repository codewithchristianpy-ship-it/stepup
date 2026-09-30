from django.db import models
from django.conf import settings


class CreditWallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wallet'
    )
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=3.00)
    total_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}: {self.balance} credits"

    def add_credits(self, amount, description, transaction_type='earned_teaching'):
        self.balance += amount
        self.total_earned += amount
        self.save()
        CreditTransaction.objects.create(
            wallet=self, amount=amount,
            transaction_type=transaction_type, description=description,
        )

    def spend_credits(self, amount, description):
        if self.balance < amount:
            raise ValueError("Not enough credits.")
        self.balance -= amount
        self.total_spent += amount
        self.save()
        CreditTransaction.objects.create(
            wallet=self, amount=-amount,
            transaction_type='spent_learning', description=description,
        )


class CreditTransaction(models.Model):
    TYPES = [
        ('signup_bonus', 'Signup Bonus'),
        ('earned_teaching', 'Earned by Teaching'),
        ('spent_learning', 'Spent on Learning'),
        ('donated', 'Donated to Community'),
        ('received', 'Received from Community'),
        ('admin_adjust', 'Admin Adjustment'),
    ]
    wallet = models.ForeignKey(CreditWallet, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=30, choices=TYPES)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.wallet.user.username}: {self.amount} ({self.transaction_type})"