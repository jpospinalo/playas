from app.routers import auth
from app.middleware.pii_filter import PIIFilterMiddleware

# Registrar middleware de ciberseguridad
app.add_middleware(PIIFilterMiddleware)

# Registrar rutas de autenticación
app.include_router(auth.router)
