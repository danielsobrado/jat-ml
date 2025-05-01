"""Authentication and authorization utilities."""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Union
from functools import wraps

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
# In auth.py, change:
from rag.api.models import Token, User, UserInDB  # Import from models

from rag.config import config

logger = logging.getLogger("auth")

# Security models
class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    username: str
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

# Initialize security utilities
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Mock user database - replace with a real database in production
fake_users_db = {
    config.auth.default_admin["username"]: {
        "username": config.auth.default_admin["username"],
        "hashed_password": pwd_context.hash(config.auth.default_admin["password"]),
        "disabled": False
    }
}

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)

def get_user(db: Dict, username: str) -> Optional[UserInDB]:
    """Get a user from the database."""
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)
    return None

def authenticate_user(db: Dict, username: str, password: str) -> Union[UserInDB, bool]:
    """Authenticate a user."""
    user = get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.auth.secret_key, algorithm="HS256")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Get the current user from token."""
    # If auth is disabled, return a default admin user
    if not config.auth.enabled:
        return User(username="admin", disabled=False)

    # No token provided
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.auth.secret_key, algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get the current active user."""
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def create_user(username: str, password: str, disabled: bool = False) -> User:
    """Create a new user."""
    if username in fake_users_db:
        raise ValueError(f"User {username} already exists")
    
    fake_users_db[username] = {
        "username": username,
        "hashed_password": get_password_hash(password),
        "disabled": disabled
    }
    
    return User(username=username, disabled=disabled)

def conditional_auth(func):
    """Decorator to conditionally apply authentication."""
    @wraps(func)
    async def wrapper(*args, current_user: User = Depends(get_current_active_user), **kwargs):
        if config.auth.enabled:
            # current_user will be filled by the dependency
            return await func(*args, current_user=current_user, **kwargs)
        else:
            # Auth is disabled, call without current_user
            return await func(*args, **kwargs)
    return wrapper