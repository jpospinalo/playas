from fastapi import APIRouter, HTTPException, status
from passlib.context import CryptContext
from app.schemas.auth import UserRegisterRequest, UserRegisterResponse

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

db_users_mock = {}

@router.post("/register", response_model=UserRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserRegisterRequest):
    if payload.correo in db_users_mock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo ya se encuentra registrado."
        )
    
    hashed_password = pwd_context.hash(payload.password)
    user_id = str(len(db_users_mock) + 1)
    
    db_users_mock[payload.correo] = {
        "id": user_id,
        "nombre_completo": payload.nombre_completo,
        "correo": payload.correo,
        "cedula": payload.cedula,
        "telefono": payload.telefono,
        "hashed_password": hashed_password
    }
    
    return UserRegisterResponse(
        id=user_id,
        nombre_completo=payload.nombre_completo,
        correo=payload.correo
    )
