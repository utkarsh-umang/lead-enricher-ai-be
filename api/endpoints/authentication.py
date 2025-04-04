from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
import logging

# Create router
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses={404: {"description": "Not found"}},
)

# Get logger
logger = logging.getLogger(__name__)

# Define request/response models
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    status: str
    message: str
    user: dict

# Hardcoded credentials (in a real app, this would be in a database)
VALID_USER = {
    "email": "utkarsh.utk123@gmail.com",
    "password": "password123",
    "name": "Utkarsh",
    "role": "admin"
}

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate a user with email and password
    
    This endpoint validates the provided credentials and returns user information on success.
    """
    try:
        logger.info(f"Login attempt for email: {request.email}")
        
        # Check if credentials match the hardcoded valid user
        if request.email == VALID_USER["email"] and request.password == VALID_USER["password"]:
            logger.info(f"Login successful for {request.email}")
            
            # Return success response with user details
            # Note: In a real application, you'd typically generate and return a JWT token here
            return LoginResponse(
                status="success",
                message="Login successful",
                user={
                    "email": VALID_USER["email"],
                    "name": VALID_USER["name"],
                    "role": VALID_USER["role"]
                }
            )
        else:
            # Return error for invalid credentials
            logger.warning(f"Invalid login attempt for {request.email}")
            raise HTTPException(status_code=401, detail="Invalid email or password")
            
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")