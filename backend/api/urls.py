from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Auth
    path('auth/register/', views.register, name='register'),
    path('auth/login/', views.login, name='login'),
    path('auth/me/', views.me, name='me'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Student
    path('student/profile/', views.student_profile, name='student-profile'),
    path('student/dashboard/', views.student_dashboard, name='student-dashboard'),

    # Investor
    path('investor/dashboard/', views.investor_dashboard, name='investor-dashboard'),
    path('investor/fund/<int:loan_id>/', views.fund_loan, name='fund-loan'),

    # Loans
    path('loans/', views.loans, name='loans'),
    path('loans/<int:loan_id>/', views.loan_detail, name='loan-detail'),
    path('loans/<int:loan_id>/pay/', views.make_payment, name='make-payment'),

    # Admin
    path('admin-panel/dashboard/', views.admin_dashboard, name='admin-dashboard'),
    path('admin-panel/loans/<int:loan_id>/approve/', views.approve_loan, name='approve-loan'),
    path('admin-panel/loans/<int:loan_id>/reject/', views.reject_loan, name='reject-loan'),
    path('admin-panel/users/<int:user_id>/block/', views.block_user, name='block-user'),

    # Tools
    path('emi-calculator/', views.emi_calculator, name='emi-calculator'),
]
