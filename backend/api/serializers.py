from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .models import User, StudentProfile, InvestorProfile, Loan, Payment


# ─── Auth Serializers ────────────────────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    college = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['email', 'full_name', 'role', 'password', 'college', 'phone']

    def create(self, validated_data):
        college = validated_data.pop('college', '')
        phone = validated_data.pop('phone', '')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()

        if user.role == 'student':
            StudentProfile.objects.create(user=user, college=college, phone=phone)
        elif user.role == 'investor':
            InvestorProfile.objects.create(user=user, phone=phone)

        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data['email'], password=data['password'])
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("Account is disabled.")
        data['user'] = user
        return data


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'role', 'is_active', 'date_joined']


# ─── Profile Serializers ─────────────────────────────────────────────────────

class StudentProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    stress_alert = serializers.SerializerMethodField()
    ai_risk_score = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = ['user', 'college', 'phone', 'stress_level', 'credit_score',
                  'stress_alert', 'ai_risk_score', 'created_at']

    def get_stress_alert(self, obj):
        return obj.stress_level > 7

    def get_ai_risk_score(self, obj):
        # Simple AI risk score: blend of credit score and stress level
        stress_penalty = obj.stress_level * 2
        score = max(0, min(100, obj.credit_score - stress_penalty))
        return round(score, 1)


class InvestorProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = InvestorProfile
        fields = ['user', 'phone', 'total_invested', 'total_returns', 'created_at']


# ─── Loan Serializers ────────────────────────────────────────────────────────

class LoanSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_email = serializers.CharField(source='student.email', read_only=True)
    investor_name = serializers.CharField(source='investor.full_name', read_only=True)
    paid_amount = serializers.SerializerMethodField()
    remaining_amount = serializers.SerializerMethodField()
    interest_label = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields = [
            'id', 'student_name', 'student_email', 'investor_name',
            'amount', 'interest_rate', 'interest_label', 'tenure_months',
            'emi', 'total_interest', 'total_payable',
            'paid_amount', 'remaining_amount',
            'purpose', 'status', 'applied_at', 'approved_at',
        ]
        read_only_fields = ['emi', 'total_interest', 'total_payable', 'status',
                            'applied_at', 'approved_at', 'investor_name']

    def get_paid_amount(self, obj):
        return round(float(obj.paid_amount()), 2)

    def get_remaining_amount(self, obj):
        return round(float(obj.remaining_amount()), 2)

    def get_interest_label(self, obj):
        labels = {0: 'Charity (0%)', 2: 'Low Interest (2%)', 4: 'Standard (4%)'}
        return labels.get(obj.interest_rate, f'{obj.interest_rate}%')


class LoanCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = ['amount', 'interest_rate', 'tenure_months', 'purpose']

    def create(self, validated_data):
        student = self.context['request'].user
        loan = Loan.objects.create(student=student, **validated_data)
        return loan


# ─── Payment Serializers ─────────────────────────────────────────────────────

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'loan', 'amount', 'payment_date', 'on_time', 'notes']
        read_only_fields = ['payment_date']


# ─── EMI Calculator ──────────────────────────────────────────────────────────

class EMICalculatorSerializer(serializers.Serializer):
    principal = serializers.FloatField()
    annual_interest_rate = serializers.FloatField()
    tenure_months = serializers.IntegerField()

    def calculate(self):
        P = self.validated_data['principal']
        rate = self.validated_data['annual_interest_rate']
        N = self.validated_data['tenure_months']

        if rate == 0:
            emi = P / N
            total_interest = 0
        else:
            R = rate / 12 / 100
            emi = (P * R * ((1 + R) ** N)) / (((1 + R) ** N) - 1)
            total_interest = (emi * N) - P

        return {
            'emi': round(emi, 2),
            'total_interest': round(total_interest, 2),
            'total_payable': round(emi * N, 2),
            'monthly_breakdown': self._get_schedule(P, rate, N, emi),
        }

    def _get_schedule(self, P, rate, N, emi):
        if rate == 0:
            return [{'month': i + 1, 'emi': round(emi, 2), 'interest': 0,
                     'principal': round(emi, 2), 'balance': round(P - emi * (i + 1), 2)}
                    for i in range(min(N, 12))]
        R = rate / 12 / 100
        schedule = []
        balance = P
        for i in range(min(N, 12)):
            interest_part = balance * R
            principal_part = emi - interest_part
            balance -= principal_part
            schedule.append({
                'month': i + 1,
                'emi': round(emi, 2),
                'interest': round(interest_part, 2),
                'principal': round(principal_part, 2),
                'balance': round(max(balance, 0), 2),
            })
        return schedule
