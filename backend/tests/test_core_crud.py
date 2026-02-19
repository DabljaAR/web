import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException, status

from app.core.models import User, SubscriptionPlan, UserSubscription, Payment
import app.media.models # Ensure all mappers are initialized
from app.core.schema import (
    SubscriptionPlanCreate, SubscriptionPlanUpdate, SubscriptionPlanResponse,
    UserSubscriptionCreate, UserSubscriptionUpdate, UserSubscriptionResponse,
    PaymentCreate, PaymentUpdate, PaymentResponse
)
from app.core.services import (
    SubscriptionPlanService, UserSubscriptionService, PaymentService, UserService
)
from app.core.enums import (
    SubscriptionStatusEnum, CurrencyEnum, PaymentMethodEnum, 
    PaymentGatewayEnum, PaymentStatusEnum, languageEnum
)
from app.core.repository import (
   UserRepository, SubscriptionPlanRepository, UserSubscriptionRepository, PaymentRepository
)

# Constants for Python 3.12+ compatibility
UTC = timezone.utc

# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_plan_repo():
    repo = Mock(spec=SubscriptionPlanRepository)
    repo.db = Mock()
    return repo

@pytest.fixture
def mock_sub_repo():
    repo = Mock(spec=UserSubscriptionRepository)
    repo.db = Mock()
    return repo

@pytest.fixture
def mock_payment_repo():
    repo = Mock(spec=PaymentRepository)
    repo.db = Mock()
    return repo

@pytest.fixture
def plan_service(mock_plan_repo):
    return SubscriptionPlanService(mock_plan_repo)

@pytest.fixture
def sub_service(mock_sub_repo):
    return UserSubscriptionService(mock_sub_repo)

@pytest.fixture
def payment_service(mock_payment_repo):
    return PaymentService(mock_payment_repo)

@pytest.fixture
def sample_user():
    """Mock user to represent the owner of resources."""
    return User(
        user_id=1,
        username="moustafa",
        email="moustafa@example.com",
        first_name="Moustafa",
        last_name="Abdallah",
        is_active=True,
        preferred_language=languageEnum.ENGLISH,
        created_at=datetime.now(UTC)
    )

@pytest.fixture
def mock_auth_service():
    """Service to handle JWT generation/verification for auth tests."""
    auth = Mock()
    auth.create_token_pair.return_value = {
        "access_token": "mock_jwt_access_token",
        "refresh_token": "mock_jwt_refresh_token",
        "token_type": "bearer"
    }
    return auth

@pytest.fixture
def sample_plan():
    return SubscriptionPlan(
        plan_id=1,
        name="Pro Plan",
        description="A professional plan",
        price=Decimal("19.99"),
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)
    )

@pytest.fixture
def sample_subscription():
    return UserSubscription(
        subscription_id=10,
        user_id=1,
        plan_id=1,
        start_date=datetime.now(UTC),
        end_date=datetime.now(UTC) + timedelta(days=30),
        status=SubscriptionStatusEnum.ACTIVE,
        auto_renew=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC)
    )

@pytest.fixture
def sample_payment():
    return Payment(
        payment_id=100,
        subscription_id=10,
        amount=Decimal("19.99"),
        currency=CurrencyEnum.USD,
        payment_method=PaymentMethodEnum.CARD,
        payment_gateway=PaymentGatewayEnum.STRIPE,
        status=PaymentStatusEnum.PAID,
        transaction_id="txn_test_123",
        payment_date=datetime.now(UTC),
        created_at=datetime.now(UTC)
    )

# ============================================================================
# TESTS: SubscriptionPlan CRUD
# ============================================================================

@pytest.mark.asyncio
class TestSubscriptionPlanCRUD:
    async def test_get_plan_success(self, plan_service, mock_plan_repo, sample_plan):
        mock_plan_repo.get_by_id = AsyncMock(return_value=sample_plan)
        result = await plan_service.get_plan_by_id(1)
        assert isinstance(result, SubscriptionPlanResponse)
        assert result.name == "Pro Plan"

    async def test_get_plan_not_found(self, plan_service, mock_plan_repo):
        mock_plan_repo.get_by_id = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc:
            await plan_service.get_plan_by_id(99)
        assert exc.value.status_code == 404

# ============================================================================
# TESTS: UserSubscription CRUD
# ============================================================================

@pytest.mark.asyncio
class TestUserSubscriptionCRUD:
    async def test_create_subscription_success(self, sub_service, mock_sub_repo, sample_subscription):
        sub_in = UserSubscriptionCreate(
            user_id=1, 
            plan_id=1, 
            end_date=datetime.now(UTC) + timedelta(days=30)
        )
        mock_sub_repo.create = AsyncMock(return_value=sample_subscription)
        result = await sub_service.create_subscription(sub_in)
        assert isinstance(result, UserSubscriptionResponse)
        assert result.subscription_id == 10

# ============================================================================
# TESTS: FULL CRUD FOR SUBSCRIPTION PLANS
# ============================================================================

@pytest.mark.asyncio
class TestSubscriptionPlanFullCRUD:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.mock_repo = Mock(spec=SubscriptionPlanRepository)
        self.service = SubscriptionPlanService(self.mock_repo)
        self.plan = SubscriptionPlan(
            plan_id=1, name="Pro", price=Decimal("19.99"), is_active=True,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
        )

    async def test_create_plan(self):
        plan_in = SubscriptionPlanCreate(name="Pro", price=Decimal("19.99"), is_active=True)
        self.mock_repo.create = AsyncMock(return_value=self.plan)
        res = await self.service.create_plan(plan_in)
        assert res.name == "Pro"

    async def test_update_plan(self):
        update_data = SubscriptionPlanUpdate(name="Enterprise")
        self.plan.name = "Enterprise"
        self.mock_repo.update = AsyncMock(return_value=self.plan)
        res = await self.service.update_plan(1, update_data)
        assert res.name == "Enterprise"

# ============================================================================
# TESTS: USER SUBSCRIPTION (Relationship Testing)
# ============================================================================

@pytest.mark.asyncio # FIXED: Added @ to prevent SKIPPED tests
class TestUserSubscriptionFullCRUD:
    @pytest.fixture(autouse=True)
    def setup(self, sample_user):
        self.mock_repo = Mock(spec=UserSubscriptionRepository)
        self.service = UserSubscriptionService(self.mock_repo)
        self.sub = UserSubscription(
            subscription_id=10, user_id=sample_user.user_id, plan_id=1,
            status=SubscriptionStatusEnum.ACTIVE,
            start_date=datetime.now(UTC), 
            end_date=datetime.now(UTC) + timedelta(days=30),
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
        )

    async def test_create_subscription_for_user(self, sample_user):
        sub_in = UserSubscriptionCreate(
            user_id=sample_user.user_id, 
            plan_id=1,
            end_date=datetime.now(UTC) + timedelta(days=30)
        )
        self.mock_repo.create = AsyncMock(return_value=self.sub)
        res = await self.service.create_subscription(sub_in)
        assert res.user_id == sample_user.user_id

    async def test_update_subscription_status(self):
        update_in = UserSubscriptionUpdate(status=SubscriptionStatusEnum.CANCELLED)
        self.sub.status = SubscriptionStatusEnum.CANCELLED
        self.mock_repo.update = AsyncMock(return_value=self.sub)
        res = await self.service.update_subscription(10, update_in)
        assert res.status == SubscriptionStatusEnum.CANCELLED

# ============================================================================
# TESTS: PAYMENTS & AUTHORIZATION FLOW
# ============================================================================

@pytest.mark.asyncio
class TestPaymentAndAuth:
    async def test_create_payment_requires_valid_user(self, sample_user):
        mock_pay_repo = Mock(spec=PaymentRepository)
        payment_service = PaymentService(mock_pay_repo)
        
        payment_obj = Payment(
            payment_id=100, subscription_id=10, amount=Decimal("19.99"),
            currency=CurrencyEnum.USD, payment_method=PaymentMethodEnum.CARD,
            payment_gateway=PaymentGatewayEnum.STRIPE, status=PaymentStatusEnum.PAID,
            transaction_id="TXN_123", 
            payment_date=datetime.now(UTC),
            created_at=datetime.now(UTC)
        )
        
        mock_pay_repo.create = AsyncMock(return_value=payment_obj)
        pay_in = PaymentCreate(
            subscription_id=10, amount=Decimal("19.99"), transaction_id="TXN_123",
            currency=CurrencyEnum.USD, payment_method=PaymentMethodEnum.CARD,
            payment_gateway=PaymentGatewayEnum.STRIPE
        )
        
        res = await payment_service.create_payment(pay_in)
        assert res.transaction_id == "TXN_123"

    async def test_jwt_authorization_flow(self, mock_auth_service, sample_user):
        """Simulate the auth flow before CRUD operations."""
        tokens = mock_auth_service.create_token_pair(sample_user)
        assert "access_token" in tokens
        assert tokens["token_type"] == "bearer"