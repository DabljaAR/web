"""Unit tests for User CRUD operations."""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException, status
from pydantic import ValidationError

from app.core.models import User
from app.core.schema import UserCreate, UserUpdate, UserResponse
from app.core.services import UserService
from app.core.repository import UserRepository
from app.core.auth import AuthService
from app.shared.enums import languageEnum
from app.core.exceptions import UserAlreadyExistsException
import app.media.models  # Register Video model for SQLAlchemy mappers


@pytest.fixture
def mock_user_repo():
    """Create a mock UserRepository."""
    repo = Mock(spec=UserRepository)
    repo.db = Mock()
    return repo


@pytest.fixture
def mock_auth_service(sample_user):
    """Create a mock AuthService."""
    auth_service = Mock(spec=AuthService)
    auth_service.get_password_hash = Mock(return_value="hashed_password")
    auth_service.verify_password = Mock(return_value=True)
    auth_service.authenticate_user = AsyncMock(return_value=sample_user)
    auth_service.create_token_pair = Mock(return_value={
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "token_type": "bearer"
    })
    return auth_service


@pytest.fixture
def user_service(mock_user_repo, mock_auth_service):
    """Create a UserService instance with mocked dependencies."""
    return UserService(mock_user_repo, mock_auth_service)


@pytest.fixture
def sample_user():
    """Create a sample User object."""
    return User(
        user_id=1,
        username="testuser",
        email="test@example.com",
        password="hashed_password",
        first_name="Test",
        last_name="User",
        preferred_language=languageEnum.ENGLISH,
        avatar_url=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        last_login=datetime.utcnow(),
        is_active = True,
        role_id=None,
        default_domain="general",
        translation_style="neutral",
        default_voice="male1",
        notif_completed=True,
        notif_credits=True,
        notif_marketing=False
    )


@pytest.fixture
def sample_user_create():
    """Create a sample UserCreate object."""
    return UserCreate(
        username="testuser",
        email="test@example.com",
        password="TestPassword123!",
        first_name="Test",
        last_name="User",
        preferred_language="en",
        avatar_url=None
    )


@pytest.fixture
def sample_user_update():
    """Create a sample UserUpdate object."""
    return UserUpdate(
        first_name="Updated",
        last_name="Name",
        preferred_language="ar"
    )


@pytest.mark.asyncio
class TestGetUserById:
    """Test get_user_by_id method."""
    
    async def test_get_user_by_id_success(self, user_service, mock_user_repo, sample_user):
        """Test successful retrieval of user by ID."""
        mock_user_repo.get_by_id = AsyncMock(return_value=sample_user)
        
        result = await user_service.get_user_by_id(1)
        
        assert isinstance(result, UserResponse)
        assert result.user_id == 1
        assert result.username == "testuser"
        assert result.email == "test@example.com"
        mock_user_repo.get_by_id.assert_called_once_with(1)
    
    async def test_get_user_by_id_not_found(self, user_service, mock_user_repo):
        """Test retrieval of non-existent user."""
        mock_user_repo.get_by_id = AsyncMock(return_value=None)
        
        with pytest.raises(HTTPException) as exc_info:
            await user_service.get_user_by_id(999)
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
class TestGetAllUsers:
    """Test get_all_users method."""
    
    async def test_get_all_users_success(self, user_service, mock_user_repo, sample_user):
        """Test successful retrieval of all users."""
        users = [sample_user]
        mock_user_repo.get_all = AsyncMock(return_value=users)
        
        result = await user_service.get_all_users(skip=0, limit=10)
        
        assert len(result) == 1
        assert isinstance(result[0], UserResponse)
        assert result[0].user_id == 1
        mock_user_repo.get_all.assert_called_once_with(skip=0, limit=10)
    
    async def test_get_all_users_empty(self, user_service, mock_user_repo):
        """Test retrieval when no users exist."""
        mock_user_repo.get_all = AsyncMock(return_value=[])
        
        result = await user_service.get_all_users(skip=0, limit=10)
        
        assert len(result) == 0
        assert isinstance(result, list)
    
    async def test_get_all_users_pagination(self, user_service, mock_user_repo, sample_user):
        """Test pagination parameters."""
        mock_user_repo.get_all = AsyncMock(return_value=[])
        
        await user_service.get_all_users(skip=10, limit=5)
        
        mock_user_repo.get_all.assert_called_once_with(skip=10, limit=5)


@pytest.mark.asyncio
class TestUpdateUser:
    """Test update_user method."""
    
    async def test_update_user_success(self, user_service, mock_user_repo, sample_user, sample_user_update):
        """Test successful user update."""
        mock_user_repo.get_by_id = AsyncMock(return_value=sample_user)
        mock_user_repo.username_exists = AsyncMock(return_value=False)
        mock_user_repo.email_exists = AsyncMock(return_value=False)
        mock_user_repo.db.commit = AsyncMock()
        mock_user_repo.db.refresh = AsyncMock()
        mock_user_repo.db.add = Mock()
        
        result = await user_service.update_user(1, sample_user_update)
        
        assert isinstance(result, UserResponse)
        assert result.first_name == "Updated"
        assert result.last_name == "Name"
        assert result.preferred_language == "ar"
        mock_user_repo.db.commit.assert_called_once()
    
    async def test_update_user_not_found(self, user_service, mock_user_repo, sample_user_update):
        """Test update of non-existent user."""
        mock_user_repo.get_by_id = AsyncMock(return_value=None)
        
        with pytest.raises(HTTPException) as exc_info:
            await user_service.update_user(999, sample_user_update)
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    
    async def test_update_user_username_conflict(self, user_service, mock_user_repo, sample_user):
        """Test update with conflicting username."""
        update_data = UserUpdate(username="existing_user")
        mock_user_repo.get_by_id = AsyncMock(return_value=sample_user)
        mock_user_repo.username_exists = AsyncMock(return_value=True)
        
        with pytest.raises(UserAlreadyExistsException) as exc_info:
            await user_service.update_user(1, update_data)
        
        assert "already registered" in str(exc_info.value.detail)
    
    async def test_update_user_email_conflict(self, user_service, mock_user_repo, sample_user):
        """Test update with conflicting email."""
        update_data = UserUpdate(email="existing@example.com")
        mock_user_repo.get_by_id = AsyncMock(return_value=sample_user)
        mock_user_repo.username_exists = AsyncMock(return_value=False)
        mock_user_repo.email_exists = AsyncMock(return_value=True)
        
        with pytest.raises(UserAlreadyExistsException) as exc_info:
            await user_service.update_user(1, update_data)
        
        assert "already registered" in str(exc_info.value.detail)
    
    async def test_update_user_password(self, user_service, mock_user_repo, sample_user):
        """Test password update."""
        update_data = UserUpdate(password="NewPassword123!")
        mock_user_repo.get_by_id = AsyncMock(return_value=sample_user)
        mock_user_repo.username_exists = AsyncMock(return_value=False)
        mock_user_repo.email_exists = AsyncMock(return_value=False)
        mock_user_repo.db.commit = AsyncMock()
        mock_user_repo.db.refresh = AsyncMock()
        mock_user_repo.db.add = Mock()
        
        result = await user_service.update_user(1, update_data)
        
        # Verify password was hashed
        user_service.auth_service.get_password_hash.assert_called_once_with("NewPassword123!")
        assert isinstance(result, UserResponse)
    
    async def test_update_user_same_username(self, user_service, mock_user_repo, sample_user):
        """Test update with same username (should not check for conflicts)."""
        update_data = UserUpdate(username="testuser", first_name="NewName")
        mock_user_repo.get_by_id = AsyncMock(return_value=sample_user)
        mock_user_repo.db.commit = AsyncMock()
        mock_user_repo.db.refresh = AsyncMock()
        mock_user_repo.db.add = Mock()
        
        result = await user_service.update_user(1, update_data)
        
        # Should not check username_exists for same username
        mock_user_repo.username_exists.assert_not_called()
        assert result.first_name == "NewName"


@pytest.mark.asyncio
class TestDeleteUser:
    """Test delete_user method."""
    
    async def test_delete_user_success(self, user_service, mock_user_repo, sample_user):
        """Test successful user deletion."""
        mock_user_repo.get_by_id = AsyncMock(return_value=sample_user)
        mock_user_repo.db.delete = AsyncMock()
        mock_user_repo.db.commit = AsyncMock()
        
        result = await user_service.delete_user(1)
        
        assert result is True
        mock_user_repo.db.delete.assert_called_once_with(sample_user)
        mock_user_repo.db.commit.assert_called_once()
    
    async def test_delete_user_not_found(self, user_service, mock_user_repo):
        """Test deletion of non-existent user."""
        mock_user_repo.get_by_id = AsyncMock(return_value=None)
        
        with pytest.raises(HTTPException) as exc_info:
            await user_service.delete_user(999)
        
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
class TestSignup:
    """Test signup method (already exists but testing for completeness)."""
    
    async def test_signup_success(self, user_service, mock_user_repo, sample_user_create, sample_user):
        """Test successful user registration."""
        mock_user_repo.username_exists = AsyncMock(return_value=False)
        mock_user_repo.email_exists = AsyncMock(return_value=False)
        mock_user_repo.db.add = Mock()
        mock_user_repo.db.commit = AsyncMock()
        mock_user_repo.db.refresh = AsyncMock()
        
        # Mock the User creation
        with patch('app.core.services.User', return_value=sample_user):
            result = await user_service.signup(sample_user_create)
        
        from app.core.schema import UserLoginResponse
        assert isinstance(result, UserLoginResponse)
        mock_user_repo.username_exists.assert_called_once()
        mock_user_repo.email_exists.assert_called_once()
        mock_user_repo.db.commit.assert_called()
    
    async def test_signup_username_exists(self, user_service, mock_user_repo, sample_user_create):
        """Test signup with existing username."""
        mock_user_repo.username_exists = AsyncMock(return_value=True)
        
        with pytest.raises(UserAlreadyExistsException):
            await user_service.signup(sample_user_create)
    
    async def test_signup_email_exists(self, user_service, mock_user_repo, sample_user_create, sample_user):
        """Test signup with existing email."""
        mock_user_repo.username_exists = AsyncMock(return_value=False)
        mock_user_repo.email_exists = AsyncMock(return_value=True)
        mock_user_repo.get_by_email = AsyncMock(return_value=sample_user)

        with pytest.raises(UserAlreadyExistsException):
            await user_service.signup(sample_user_create)

    async def test_signup_google_only_email_guides_to_google(self, user_service, mock_user_repo, sample_user_create, sample_user):
        """Signup with an email belonging to a Google-only account should guide to Google."""
        # A Google-only account has an empty password.
        google_user = sample_user
        google_user.password = ""
        mock_user_repo.username_exists = AsyncMock(return_value=False)
        mock_user_repo.email_exists = AsyncMock(return_value=True)
        mock_user_repo.get_by_email = AsyncMock(return_value=google_user)

        with pytest.raises(UserAlreadyExistsException) as exc_info:
            await user_service.signup(sample_user_create)

        assert "Google" in str(exc_info.value.detail)


class TestPasswordByteLimitValidation:
    """Test UTF-8 byte length password validation for bcrypt."""

    def test_user_create_accepts_exactly_72_ascii_bytes(self):
        payload = UserCreate(
            username="bytesok",
            email="bytesok@example.com",
            password="A" * 72,
            first_name="Bytes",
            last_name="Ok",
            preferred_language="en",
            avatar_url=None,
        )

        assert payload.password == "A" * 72

    def test_user_create_rejects_73_ascii_bytes(self):
        with pytest.raises(ValidationError, match="must not exceed 72 bytes"):
            UserCreate(
                username="bytestoolong",
                email="bytestoolong@example.com",
                password="A" * 73,
                first_name="Bytes",
                last_name="TooLong",
                preferred_language="en",
                avatar_url=None,
            )

    def test_user_create_rejects_multibyte_password_over_72_bytes(self):
        # Arabic chars are multibyte in UTF-8 and exceed the 72-byte bcrypt limit.
        password = "Aa1" + ("أ" * 35)

        with pytest.raises(ValidationError, match="must not exceed 72 bytes"):
            UserCreate(
                username="arabicbytes",
                email="arabicbytes@example.com",
                password=password,
                first_name="Arabic",
                last_name="Bytes",
                preferred_language="ar",
                avatar_url=None,
            )

    def test_user_update_rejects_password_over_72_bytes(self):
        with pytest.raises(ValidationError, match="must not exceed 72 bytes"):
            UserUpdate(password="A" * 73, first_name="Updated")


@pytest.mark.asyncio
class TestChangePassword:
    """Test change_password method, including Google-only accounts."""

    async def test_change_password_with_correct_old_password(self, user_service, mock_user_repo, sample_user):
        """User with a password can change it when providing the correct old one."""
        mock_user_repo.get_by_id = AsyncMock(return_value=sample_user)
        mock_user_repo.db.commit = AsyncMock()
        mock_user_repo.db.add = Mock()

        result = await user_service.change_password(1, "hashed_password", "NewPassword123!")

        assert result["message"] == "Password changed successfully"
        user_service.auth_service.verify_password.assert_called_once()
        user_service.auth_service.get_password_hash.assert_called_once_with("NewPassword123!")

    async def test_change_password_with_wrong_old_password(self, user_service, mock_user_repo, sample_user):
        """Wrong old password is rejected for users who have a password."""
        user_service.auth_service.verify_password = Mock(return_value=False)
        mock_user_repo.get_by_id = AsyncMock(return_value=sample_user)

        with pytest.raises(HTTPException) as exc_info:
            await user_service.change_password(1, "wrong", "NewPassword123!")

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_change_password_google_only_skips_old_password(self, user_service, mock_user_repo, sample_user):
        """Google-only users (empty password) can set a password without the old one."""
        google_user = sample_user
        google_user.password = ""
        mock_user_repo.get_by_id = AsyncMock(return_value=google_user)
        mock_user_repo.db.commit = AsyncMock()
        mock_user_repo.db.add = Mock()

        result = await user_service.change_password(1, None, "NewPassword123!")

        assert result["message"] == "Password changed successfully"
        # Old password must NOT be verified since the account has none.
        user_service.auth_service.verify_password.assert_not_called()
        user_service.auth_service.get_password_hash.assert_called_once_with("NewPassword123!")


@pytest.mark.asyncio
class TestGoogleAuth:
    """Test google_auth security handling."""

    async def test_google_auth_links_verified_email_to_existing_user(
        self, user_service, mock_user_repo, mock_auth_service, sample_user
    ):
        """A verified Google email is linked to an existing email-only account."""
        sample_user.google_id = None
        mock_auth_service.verify_google_token = AsyncMock(return_value={
            "sub": "g-123",
            "email": "test@example.com",
            "email_verified": "true",
            "given_name": "Test",
            "family_name": "User",
            "picture": "",
        })
        mock_user_repo.get_by_google_id = AsyncMock(return_value=None)
        mock_user_repo.get_by_email = AsyncMock(return_value=sample_user)
        mock_user_repo.username_exists = AsyncMock(return_value=False)
        mock_user_repo.db.commit = AsyncMock()
        mock_user_repo.db.add = Mock()
        mock_user_repo.db.refresh = AsyncMock()

        result = await user_service.google_auth("credential")

        assert sample_user.google_id == "g-123"
        from app.core.schema import UserLoginResponse
        assert isinstance(result, UserLoginResponse)

    async def test_google_auth_rejects_unverified_email_link(
        self, user_service, mock_user_repo, mock_auth_service, sample_user
    ):
        """An unverified Google email must not be linked to an existing account."""
        sample_user.google_id = None
        mock_auth_service.verify_google_token = AsyncMock(return_value={
            "sub": "g-123",
            "email": "test@example.com",
            "email_verified": "false",
        })
        mock_user_repo.get_by_google_id = AsyncMock(return_value=None)
        mock_user_repo.get_by_email = AsyncMock(return_value=sample_user)

        from app.core.exceptions import InvalidCredentialsException
        with pytest.raises(InvalidCredentialsException):
            await user_service.google_auth("credential")

    async def test_google_auth_rejects_conflicting_google_id(
        self, user_service, mock_user_repo, mock_auth_service, sample_user
    ):
        """An email already linked to a different Google account must not be taken over."""
        sample_user.google_id = "other-google-id"
        mock_auth_service.verify_google_token = AsyncMock(return_value={
            "sub": "g-123",
            "email": "test@example.com",
            "email_verified": "true",
        })
        mock_user_repo.get_by_google_id = AsyncMock(return_value=None)
        mock_user_repo.get_by_email = AsyncMock(return_value=sample_user)

        from app.core.exceptions import InvalidCredentialsException
        with pytest.raises(InvalidCredentialsException):
            await user_service.google_auth("credential")






