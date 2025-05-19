# rag/api/models.py
"""Pydantic models for API requests and responses."""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime # Import datetime

# --- Keep existing models (Token, NewUserRequest, CategoryItem, etc.) ---
class Token(BaseModel):
    access_token: str
    token_type: str

class NewUserRequest(BaseModel):
    username: str
    password: str
    disabled: bool = False

# Item models
class CategoryItem(BaseModel):
    code: str
    name: str
    description: str
    hierarchy: str = ""
    metadata: Dict = Field(default_factory=dict)

class BatchAddRequest(BaseModel):
    items: List[CategoryItem]
    collection_name: str

# Search models
class SimilarityResult(BaseModel):
    code: str
    name: str
    description: str = ""  # Add description field with default empty string
    hierarchy: str
    similarity_score: float
    metadata: Dict

class SimilarityResponse(BaseModel):
    query: str
    collection_name: str
    results: List[SimilarityResult]

class MultiCollectionSearchResponse(BaseModel):
    query: str
    results: Dict[str, List[SimilarityResult]]

# Collection models
class CollectionInfo(BaseModel):
    name: str
    count: int

class ListCollectionsResponse(BaseModel):
    collections: List[CollectionInfo]

# Status models
class StatusResponse(BaseModel):
    status: str
    chroma_connected: bool
    collections: List[str]
    auth_enabled: bool

class User(BaseModel):
    username: str
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

# --- RAG Info Models ---
class RagInfoItemBase(BaseModel):
    key: str = Field(..., description="Unique key for the information")
    description: str = Field(..., description="The textual information content")

class RagInfoItemCreate(RagInfoItemBase):
    pass # Same fields as base for creation

class RagInfoItemUpdate(BaseModel):
    # Only description is updatable via the frontend modal
    description: str = Field(..., description="The updated textual information")

class RagInfoItem(RagInfoItemBase):
    id: str = Field(..., description="Unique identifier (same as key in this implementation)")
    createdAt: datetime = Field(..., description="Creation timestamp")
    updatedAt: datetime = Field(..., description="Last update timestamp")

    # Use model_config for Pydantic V2
    model_config = ConfigDict(from_attributes=True)

class RagInfoPageResponse(BaseModel):
    items: List[RagInfoItem]
    totalCount: int = Field(..., description="Total number of items matching filters")
    totalPages: int = Field(..., description="Total number of pages")
    currentPage: int = Field(..., description="The current page number (1-based)")

# --- Chat Models ---
class ChatMessagePy(BaseModel):
    id: Optional[str] = None
    role: str # "user", "assistant", "system"
    content: str
    # createdAt: Optional[datetime] = None # Keep it simple for now

class GenAIChatRequest(BaseModel):
    messages: List[ChatMessagePy]
    stream: Optional[bool] = Field(default=True)
    model: Optional[str] = None
    # max_tokens: Optional[int] = None # Example: if you want to pass max_tokens

class GenAIChatResponseChunk(BaseModel):
    text: Optional[str] = None
    done: bool
    error: Optional[str] = None