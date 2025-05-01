"""Client for the Classification API."""
import requests
import json
from typing import List, Dict, Optional

class ClassificationClient:
    """Client for interacting with the Classification API."""
    
    def __init__(
        self, 
        base_url: str = None,
        api_key: str = None,
        headers: Dict[str, str] = None,
        verify_ssl: bool = True
    ):
        """Initialize the RAG Client with custom settings.
        
        Args:
            base_url: Base URL of the API (e.g., 'http://localhost:8090')
            api_key: Optional API key for authentication
            headers: Optional additional headers to send with each request
            verify_ssl: Whether to verify SSL certificates. Set to False for self-signed certs.
        """
        self.base_url = base_url.rstrip('/')
        self.username = None
        self.password = None
        self.token = None
        self.auth_enabled = True
        
        # Check if authentication is enabled
        self._check_auth_status()
        
        # Get token if authentication is enabled and credentials are provided
        if self.auth_enabled and self.username and self.password:
            self._get_token()
    
    def _check_auth_status(self):
        """Check if authentication is enabled on the server."""
        try:
            status = self.check_status()
            self.auth_enabled = status.get("auth_enabled", True)
        except Exception as e:
            # Assume authentication is enabled if we can't determine
            self.auth_enabled = True
    
    def _get_token(self):
        """Get OAuth2 token."""
        if not self.auth_enabled:
            return
        
        if not self.username or not self.password:
            raise ValueError("Username and password required for authentication")
        
        url = f"{self.base_url}/token"
        data = {
            "username": self.username,
            "password": self.password
        }
        
        response = requests.post(url, data=data)
        if response.status_code == 200:
            self.token = response.json().get("access_token")
        else:
            raise Exception(f"Failed to get token: {response.text}")
    
    def _get_headers(self):
        """Get headers for API requests."""
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.auth_enabled and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        return headers
    
    def check_status(self):
        """Check API status."""
        url = f"{self.base_url}/"
        response = requests.get(url)
        return response.json()
    
    def list_collections(self):
        """List all available collections."""
        url = f"{self.base_url}/collections"
        response = requests.get(url)
        return response.json()
    
    def create_collection(self, collection_name: str):
        """Create a new collection.
        
        Args:
            collection_name: Name of the collection to create
            
        Returns:
            API response
        """
        url = f"{self.base_url}/collection/{collection_name}"
        response = requests.post(url, headers=self._get_headers())
        
        if response.status_code == 401 and self.auth_enabled:
            # If token might be expired, try to refresh it
            self._get_token()
            response = requests.post(url, headers=self._get_headers())
        
        return response.json()
    
    def add_batch(self, items: List[Dict], collection_name: str):
        """Add a batch of items to the collection.
        
        Args:
            items: List of items with code, name, description, etc.
            collection_name: Collection name
        
        Returns:
            API response
        """
        url = f"{self.base_url}/add_batch"
        data = {
            "items": items,
            "collection_name": collection_name
        }
        
        response = requests.post(url, json=data, headers=self._get_headers())
        
        if response.status_code == 401 and self.auth_enabled:
            # If token might be expired, try to refresh it
            self._get_token()
            response = requests.post(url, json=data, headers=self._get_headers())
        
        return response.json()
    
    def search(self, query: str, collection_name: str, limit: int = 5):
        """Search for similar items in a specific collection.
        
        Args:
            query: Text query to search for
            collection_name: Collection name
            limit: Maximum number of results to return
        
        Returns:
            Search results
        """
        url = f"{self.base_url}/search"
        params = {
            "query": query,
            "collection_name": collection_name,
            "limit": limit
        }
        
        response = requests.get(url, params=params)
        return response.json()
    
    def search_all(self, query: str, limit_per_collection: int = 3, min_score: float = 0.0):
        """Search for similar items across all collections.
        
        Args:
            query: Text query to search for
            limit_per_collection: Maximum number of results per collection
            min_score: Minimum similarity score (0-1)
        
        Returns:
            Search results from all collections
        """
        url = f"{self.base_url}/search_all"
        params = {
            "query": query,
            "limit_per_collection": limit_per_collection,
            "min_score": min_score
        }
        
        response = requests.get(url, params=params)
        return response.json()
    
    def delete_collection(self, collection_name: str):
        """Delete a collection.
        
        Args:
            collection_name: Name of the collection to delete
        
        Returns:
            API response
        """
        url = f"{self.base_url}/collection/{collection_name}"
        response = requests.delete(url, headers=self._get_headers())
        
        if response.status_code == 401 and self.auth_enabled:
            # If token might be expired, try to refresh it
            self._get_token()
            response = requests.delete(url, headers=self._get_headers())
        
        return response.json()
    
    def create_user(self, username: str, password: str, disabled: bool = False):
        """Create a new user (admin only).
        
        Args:
            username: New user's username
            password: New user's password
            disabled: Whether the user should be disabled initially
            
        Returns:
            API response
        """
        if not self.auth_enabled:
            return {"message": "Authentication is disabled, user not created"}
        
        url = f"{self.base_url}/users"
        data = {
            "username": username,
            "password": password,
            "disabled": disabled
        }
        
        response = requests.post(url, json=data, headers=self._get_headers())
        
        if response.status_code == 401:
            # If token might be expired, try to refresh it
            self._get_token()
            response = requests.post(url, json=data, headers=self._get_headers())
        
        return response.json()
    
    def get_current_user(self):
        """Get current user information.
        
        Returns:
            User information
        """
        if not self.auth_enabled:
            return {"username": "anonymous", "disabled": False}
        
        url = f"{self.base_url}/users/me"
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 401:
            # If token might be expired, try to refresh it
            self._get_token()
            response = requests.get(url, headers=self._get_headers())
        
        return response.json()


# Example usage
if __name__ == "__main__":
    # Initialize client - it will automatically detect if auth is enabled
    client = ClassificationClient(
        base_url="http://localhost:8090",
        username="admin",  # These will be used only if auth is enabled
        password="admin"
    )
    
    # Check API status
    status = client.check_status()
    print("API Status:", json.dumps(status, indent=2))
    print(f"Authentication enabled: {client.auth_enabled}")
    
    # Create a collection
    collection_name = "unspsc_categories"
    try:
        create_result = client.create_collection(collection_name)
        print(f"Created collection: {json.dumps(create_result, indent=2)}")
    except Exception as e:
        print(f"Error creating collection: {e}")
    
    # Add some sample items
    sample_items = [
        {
            "code": "43211503",
            "name": "Notebook computer",
            "description": "A portable personal computer that typically weighs under 5 pounds.",
            "hierarchy": "Information Technology > Computer Equipment > Computers > Notebook computer",
            "metadata": {
                "category": "electronics",
                "type": "good"
            }
        },
        {
            "code": "43211507",
            "name": "Desktop computer",
            "description": "A personal computer that is designed to be used in a single location.",
            "hierarchy": "Information Technology > Computer Equipment > Computers > Desktop computer"
        }
    ]
    
    try:
        add_result = client.add_batch(sample_items, collection_name)
        print("Added items:", json.dumps(add_result, indent=2))
    except Exception as e:
        print(f"Error adding items: {e}")
    
    # Search for similar items
    search_result = client.search("laptop computer", collection_name)
    print("Search results:", json.dumps(search_result, indent=2))