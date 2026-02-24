from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
import math


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('investor', 'Investor'),
        ('admin', 'Admin'),
    ]
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    objects = UserManager()

    def __str__(self):
        return f"{self.email} ({self.role})"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    college = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    stress_level = models.IntegerField(default=0)  # 1–10
    credit_score = models.FloatField(default=100.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def update_credit_score(self):
        loans = self.user.loans.all()
        total_payments = Payment.objects.filter(loan__student=self.user).count()
        on_time_payments = Payment.objects.filter(loan__student=self.user, on_time=True).count()
        if total_payments > 0:
            self.credit_score = round((on_time_payments / total_payments) * 100, 2)
        self.save()

    def __str__(self):
        return f"Student: {self.user.email}"


class InvestorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='investor_profile')
    phone = models.CharField(max_length=15, blank=True)
    total_invested = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_returns = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Investor: {self.user.email}"


class Loan(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('active', 'Active'),
        ('completed', 'Completed'),
    ]
    INTEREST_CHOICES = [
        (0, 'Charity (0%)'),
        (2, 'Low Interest (2%)'),
        (4, 'Standard (4%)'),
    ]

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='loans')
    investor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='funded_loans')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    interest_rate = models.IntegerField(choices=INTEREST_CHOICES, default=2)
    tenure_months = models.IntegerField(default=12)
    emi = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_interest = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_payable = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    purpose = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    applied_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    def calculate_emi(self):
        P = float(self.amount)
        annual_rate = self.interest_rate
        N = self.tenure_months

        if annual_rate == 0:
            emi = P / N
            total_interest = 0
        else:
            R = annual_rate / 12 / 100
            emi = (P * R * ((1 + R) ** N)) / (((1 + R) ** N) - 1)
            total_interest = (emi * N) - P

        self.emi = round(emi, 2)
        self.total_interest = round(total_interest, 2)
        self.total_payable = round(emi * N, 2)

    def save(self, *args, **kwargs):
        self.calculate_emi()
        super().save(*args, **kwargs)

    def paid_amount(self):
        return sum(p.amount for p in self.payments.all())

    def remaining_amount(self):
        return float(self.total_payable) - float(self.paid_amount())

    def __str__(self):
        return f"Loan #{self.id} - {self.student.email} - ₹{self.amount}"


class Payment(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    on_time = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Payment ₹{self.amount} for Loan #{self.loan.id}"
