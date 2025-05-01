"""Authentication routes."""
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from rag.config import config
from rag.api.auth import (
    authenticate_user, create_access_token, get_current_active_user, 
    fake_users_db, create_user
)
from rag.api.models import Token, User, NewUserRequest

logger = logging.getLogger("auth_routes")

router = APIRouter(tags=["authentication"])

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 compatible token login, get an access token for future requests."""
    if not config.auth.enabled:
        # If auth is disabled, return a dummy token
        access_token = create_access_token(data={"sub": "admin"})
        return {"access_token": access_token, "token_type": "bearer"}
    
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=config.auth.token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/users", response_model=User)
async def create_new_user(user_request: NewUserRequest, current_user: User = Depends(get_current_active_user)):
    """Create a new user (admin only)."""
    if not config.auth.enabled:
        return {"message": "Authentication is disabled, user not created"}
    
    if current_user.username != config.auth.default_admin["username"]:
        raise HTTPException(status_code=403, detail="Only admin can create users")
    
    try:
        return create_user(
            username=user_request.username,
            password=user_request.password,
            disabled=user_request.disabled
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    """Get current user information."""
    return current_user