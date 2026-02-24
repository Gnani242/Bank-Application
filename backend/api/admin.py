from django.contrib import admin
from .models import User, StudentProfile, InvestorProfile, Loan, Payment


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'full_name', 'role', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active']
    search_fields = ['email', 'full_name']
    ordering = ['-date_joined']


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'stress_level', 'credit_score', 'college']
    list_filter = ['stress_level']


@admin.register(InvestorProfile)
class InvestorProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'total_invested', 'total_returns']


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ['id', 'student', 'investor', 'amount', 'interest_rate', 'tenure_months', 'emi', 'status', 'applied_at']
    list_filter = ['status', 'interest_rate']
    search_fields = ['student__email']
    actions = ['approve_loans', 'reject_loans']

    def approve_loans(self, request, queryset):
        from django.utils import timezone
        queryset.filter(status='pending').update(status='approved', approved_at=timezone.now())
    approve_loans.short_description = "Approve selected loans"

    def reject_loans(self, request, queryset):
        queryset.filter(status='pending').update(status='rejected')
    reject_loans.short_description = "Reject selected loans"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['loan', 'amount', 'payment_date', 'on_time']
    list_filter = ['on_time']
