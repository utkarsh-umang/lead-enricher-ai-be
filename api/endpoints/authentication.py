from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
import logging
from datetime import datetime
from passlib.context import CryptContext
from typing import Optional
from bson import ObjectId
from utils.db import MongoDB

# Create router
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses={404: {"description": "Not found"}},
)

# Get logger
logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Define request/response models
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    agency_id: str
    role: str = "user"  # Default role is user

class AuthResponse(BaseModel):
    status: str
    message: str
    user: dict = None

# Helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def get_database():
    """Get database connection safely"""
    db = MongoDB.get_db()
    if db is None:
        logger.error("Failed to get database connection")
        raise HTTPException(status_code=500, detail="Database connection error")
    return db

@router.post("/signup", response_model=AuthResponse)
async def signup(request: SignupRequest):
    """
    Register a new user
    
    This endpoint creates a new user in the database with the provided information
    and associates them with an agency.
    """
    try:
        logger.info(f"Signup attempt for email: {request.email} with agency_id: {request.agency_id}")
        
        # Get database connection
        db = get_database()
        
        # Check if user already exists
        existing_user = db.users.find_one({"email": request.email})
        if existing_user is not None:
            logger.warning(f"Signup failed: User {request.email} already exists")
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Verify agency exists (optional - uncomment if you want to enforce agency existence)
        try:
            agency_id_obj = ObjectId(request.agency_id)
            agency = db.agencies.find_one({"_id": agency_id_obj})
            if agency is None:
                logger.warning(f"Signup failed: Agency with ID {request.agency_id} does not exist")
                raise HTTPException(status_code=400, detail="Agency does not exist")
        except Exception as e:
            logger.warning(f"Invalid agency_id format: {request.agency_id}")
            raise HTTPException(status_code=400, detail="Invalid agency ID format")
        
        # Create new user document
        new_user = {
            "email": request.email,
            "name": request.name,
            "role": request.role,
            "agency_id": request.agency_id,  # Store the agency ID
            "hashed_password": get_password_hash(request.password),
            "created_at": datetime.utcnow()
        }
        
        # Insert user into database
        result = db.users.insert_one(new_user)
        
        logger.info(f"User created successfully: {request.email} for agency: {request.agency_id}")
        
        # Return success response (without password)
        return AuthResponse(
            status="success",
            message="User created successfully",
            user={
                "id": str(result.inserted_id),
                "email": request.email,
                "name": request.name,
                "role": request.role,
                "agency_id": request.agency_id
            }
        )
            
    except HTTPException:
        # Re-raise HTTP exceptions to preserve status code
        raise
    except Exception as e:
        logger.error(f"Signup error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Signup failed: {str(e)}")

@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    Authenticate a user with email and password
    
    This endpoint validates the provided credentials and returns user information on success.
    """
    try:
        logger.info(f"Login attempt for email: {request.email}")
        
        # Get database connection
        db = get_database()
        
        # Find user by email
        user = db.users.find_one({"email": request.email})
        
        # Verify user exists and password is correct
        if user is None or not verify_password(request.password, user["hashed_password"]):
            logger.warning(f"Invalid login attempt for {request.email}")
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        logger.info(f"Login successful for {request.email} (Agency ID: {user.get('agency_id', 'None')})")
        
        # Return success response with user details
        return AuthResponse(
            status="success",
            message="Login successful",
            user={
                "id": str(user["_id"]),
                "email": user["email"],
                "name": user["name"],
                "role": user["role"],
                "agency_id": user.get("agency_id", None)
            }
        )
            
    except HTTPException:
        # Re-raise HTTP exceptions to preserve status code
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

# Agency Management Endpoints

class AgencyCreate(BaseModel):
    name: str
    description: Optional[str] = None

@router.post("/agencies", response_model=dict)
async def create_agency(request: AgencyCreate):
    """
    Create a new agency
    
    This endpoint creates a new agency in the database.
    """
    try:
        logger.info(f"Creating new agency: {request.name}")
        
        # Get database connection safely
        db = get_database()
        
        # Create new agency document
        new_agency = {
            "name": request.name,
            "description": request.description,
            "created_at": datetime.utcnow()
        }
        
        # Insert agency into database
        result = db.agencies.insert_one(new_agency)
        
        logger.info(f"Agency created successfully: {request.name} with ID: {result.inserted_id}")
        
        # Return success response
        return {
            "status": "success",
            "message": "Agency created successfully",
            "agency": {
                "id": str(result.inserted_id),
                "name": request.name,
                "description": request.description
            }
        }
            
    except HTTPException:
        # Re-raise HTTP exceptions to preserve status code
        raise
    except Exception as e:
        logger.error(f"Agency creation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Agency creation failed: {str(e)}")

@router.get("/agencies", response_model=list)
async def list_agencies():
    """
    List all agencies
    
    This endpoint returns a list of all agencies in the database.
    """
    try:
        # Get database connection safely
        db = get_database()
        
        # Get all agencies
        agencies = list(db.agencies.find())
        
        # Format agencies for response
        formatted_agencies = []
        for agency in agencies:
            formatted_agencies.append({
                "id": str(agency["_id"]),
                "name": agency["name"],
                "description": agency.get("description", None)
            })
        
        return formatted_agencies
            
    except Exception as e:
        logger.error(f"Error listing agencies: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list agencies: {str(e)}")