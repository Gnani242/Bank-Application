from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.db.models import Sum, Count

from .models import User, StudentProfile, InvestorProfile, Loan, Payment
from .serializers import (
    RegisterSerializer, LoginSerializer, UserSerializer,
    StudentProfileSerializer, InvestorProfileSerializer,
    LoanSerializer, LoanCreateSerializer,
    PaymentSerializer, EMICalculatorSerializer,
)


# ─── Auth ────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


# ─── Student Views ────────────────────────────────────────────────────────────

@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def student_profile(request):
    try:
        profile = request.user.student_profile
    except StudentProfile.DoesNotExist:
        return Response({'error': 'Not a student'}, status=status.HTTP_403_FORBIDDEN)

    if request.method == 'GET':
        serializer = StudentProfileSerializer(profile)
        return Response(serializer.data)

    if request.method == 'PATCH':
        serializer = StudentProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            data = serializer.data
            # Check stress alert
            if profile.stress_level > 7:
                data['stress_message'] = "😔 Take a break. Your mental health matters. Contact Support."
            return Response(data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_dashboard(request):
    try:
        profile = request.user.student_profile
    except StudentProfile.DoesNotExist:
        return Response({'error': 'Not a student'}, status=status.HTTP_403_FORBIDDEN)

    loans = Loan.objects.filter(student=request.user)
    active_loan = loans.filter(status__in=['approved', 'active']).first()

    total_paid = Payment.objects.filter(
        loan__student=request.user
    ).aggregate(total=Sum('amount'))['total'] or 0

    profile_data = StudentProfileSerializer(profile).data
    loans_data = LoanSerializer(loans, many=True).data

    return Response({
        'profile': profile_data,
        'loans': loans_data,
        'active_loan': LoanSerializer(active_loan).data if active_loan else None,
        'total_paid': float(total_paid),
        'stress_alert': profile.stress_level > 7,
        'tips': get_financial_tips(),
    })


# ─── Investor Views ───────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def investor_dashboard(request):
    try:
        profile = request.user.investor_profile
    except InvestorProfile.DoesNotExist:
        return Response({'error': 'Not an investor'}, status=status.HTTP_403_FORBIDDEN)

    funded_loans = Loan.objects.filter(investor=request.user)
    pending_loans = Loan.objects.filter(status='pending')

    # Analytics per interest mode
    by_mode = {
        'charity': funded_loans.filter(interest_rate=0).count(),
        'low_interest': funded_loans.filter(interest_rate=2).count(),
        'standard': funded_loans.filter(interest_rate=4).count(),
    }

    return Response({
        'profile': InvestorProfileSerializer(profile).data,
        'funded_loans': LoanSerializer(funded_loans, many=True).data,
        'available_loans': LoanSerializer(pending_loans, many=True).data,
        'analytics': {
            'total_invested': float(profile.total_invested),
            'total_returns': float(profile.total_returns),
            'loans_funded': funded_loans.count(),
            'by_mode': by_mode,
        },
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def fund_loan(request, loan_id):
    try:
        profile = request.user.investor_profile
    except InvestorProfile.DoesNotExist:
        return Response({'error': 'Not an investor'}, status=status.HTTP_403_FORBIDDEN)

    try:
        loan = Loan.objects.get(id=loan_id, status='approved')
    except Loan.DoesNotExist:
        return Response({'error': 'Loan not available for funding'}, status=status.HTTP_404_NOT_FOUND)

    loan.investor = request.user
    loan.status = 'active'
    loan.save()

    # Update investor totals
    profile.total_invested += loan.amount
    profile.save()

    return Response({'message': 'Loan funded successfully!', 'loan': LoanSerializer(loan).data})


# ─── Loan Views ───────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def loans(request):
    if request.method == 'GET':
        user_loans = Loan.objects.filter(student=request.user)
        return Response(LoanSerializer(user_loans, many=True).data)

    if request.method == 'POST':
        serializer = LoanCreateSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            loan = serializer.save()
            return Response(LoanSerializer(loan).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def loan_detail(request, loan_id):
    try:
        loan = Loan.objects.get(id=loan_id)
        if loan.student != request.user and loan.investor != request.user and not request.user.is_staff:
            return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
    except Loan.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response(LoanSerializer(loan).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def make_payment(request, loan_id):
    try:
        loan = Loan.objects.get(id=loan_id, student=request.user, status='active')
    except Loan.DoesNotExist:
        return Response({'error': 'Active loan not found'}, status=status.HTTP_404_NOT_FOUND)

    amount = request.data.get('amount', loan.emi)
    payment = Payment.objects.create(loan=loan, amount=amount, on_time=True)

    # Check if loan is completed
    if loan.remaining_amount() <= 0:
        loan.status = 'completed'
        loan.save()

    # Update credit score
    try:
        profile = loan.student.student_profile
        profile.update_credit_score()
    except Exception:
        pass

    return Response({
        'message': 'Payment successful! 🎉',
        'payment': PaymentSerializer(payment).data,
        'loan': LoanSerializer(loan).data,
    })


# ─── Admin Views ──────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_dashboard(request):
    if not request.user.is_staff and request.user.role != 'admin':
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)

    total_users = User.objects.count()
    total_students = User.objects.filter(role='student').count()
    total_investors = User.objects.filter(role='investor').count()
    total_loans = Loan.objects.count()
    active_loans = Loan.objects.filter(status='active').count()
    pending_loans = Loan.objects.filter(status='pending').count()
    total_disbursed = Loan.objects.filter(status__in=['active', 'completed']).aggregate(
        t=Sum('amount'))['t'] or 0
    high_stress = StudentProfile.objects.filter(stress_level__gt=7).count()

    all_loans = Loan.objects.all().order_by('-applied_at')[:20]

    return Response({
        'stats': {
            'total_users': total_users,
            'total_students': total_students,
            'total_investors': total_investors,
            'total_loans': total_loans,
            'active_loans': active_loans,
            'pending_loans': pending_loans,
            'total_disbursed': float(total_disbursed),
            'high_stress_students': high_stress,
        },
        'recent_loans': LoanSerializer(all_loans, many=True).data,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def approve_loan(request, loan_id):
    if not request.user.is_staff and request.user.role != 'admin':
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)
    try:
        loan = Loan.objects.get(id=loan_id, status='pending')
        loan.status = 'approved'
        loan.approved_at = timezone.now()
        loan.save()
        return Response({'message': 'Loan approved!', 'loan': LoanSerializer(loan).data})
    except Loan.DoesNotExist:
        return Response({'error': 'Pending loan not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def reject_loan(request, loan_id):
    if not request.user.is_staff and request.user.role != 'admin':
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)
    try:
        loan = Loan.objects.get(id=loan_id, status='pending')
        loan.status = 'rejected'
        loan.save()
        return Response({'message': 'Loan rejected.'})
    except Loan.DoesNotExist:
        return Response({'error': 'Pending loan not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def block_user(request, user_id):
    if not request.user.is_staff and request.user.role != 'admin':
        return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)
    try:
        user = User.objects.get(id=user_id)
        user.is_active = not user.is_active
        user.save()
        action = 'unblocked' if user.is_active else 'blocked'
        return Response({'message': f'User {action} successfully.'})
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)


# ─── EMI Calculator ──────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def emi_calculator(request):
    serializer = EMICalculatorSerializer(data=request.data)
    if serializer.is_valid():
        result = serializer.calculate()
        return Response(result)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── Financial Tips ───────────────────────────────────────────────────────────

def get_financial_tips():
    return [
        "💡 Pay your EMI on time to maintain a healthy credit score.",
        "📊 Choose 0% charity loans if available — save more, stress less.",
        "🎯 Track your monthly expenses with the 50-30-20 rule.",
        "🔒 Never share your banking credentials with anyone.",
        "📚 Invest in skills that increase your earning potential.",
        "🌱 Start an emergency fund with 3 months of expenses.",
    ]
