from pydantic import BaseModel, EmailStr, Field

class UserRegisterRequest(BaseModel):
    nombre_completo: str = Field(..., min_length=3, max_length=100)
    correo: EmailStr
    cedula: str = Field(..., pattern=r"^\d{7,10}$")
    telefono: str = Field(..., pattern=r"^\+?\d{10,12}$")
    password: str = Field(..., min_length=8)

class UserRegisterResponse(BaseModel):
    id: str
    nombre_completo: str
    correo: str
    mensaje: str = "Usuario registrado exitosamente"
