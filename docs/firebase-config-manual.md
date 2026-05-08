# Configuración manual Firebase

> Esta página documenta todos los pasos que hay que hacer **a mano** en Firebase Console antes de que el proyecto funcione. Aplica a un proyecto de Firebase recién creado.

Fuente original: página `claude:proyecto-playas / Configuración manual Firebase` en Notion.

---

## 1. Autenticación (Authentication)

1. En Firebase Console, ir a **Build → Authentication**.
2. Clic en **Comenzar** (o **Get started**).
3. En la pestaña **Sign-in method**, habilitar el proveedor **Correo electrónico/contraseña**.
4. Dejar **Vínculo de correo electrónico (inicio de sesión sin contraseña)** deshabilitado.
5. Guardar.

No se requiere ninguna otra configuración de autenticación.

---

## 2. Firestore Database

### Crear la base de datos

1. Ir a **Build → Firestore Database**.
2. Clic en **Crear base de datos**.
3. Seleccionar **Modo de producción** (las reglas de abajo reemplazan las genéricas).
4. Elegir la región más cercana (ej. `us-east1`).
5. Clic en **Listo**.

### Reglas de seguridad

Una vez creada la base de datos, ir a la pestaña **Reglas** y reemplazar el contenido con:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    function isAdmin() {
      return request.auth != null &&
        get(/databases/$(database)/documents/users/$(request.auth.uid))
          .data.role in ['admin', 'super-admin'];
    }

    match /users/{uid} {
      allow read: if request.auth.uid == uid || isAdmin();
      allow create: if request.auth.uid == uid;
      allow update: if request.auth.uid == uid &&
                       !('role' in request.resource.data.diff(resource.data).affectedKeys());
      allow list: if isAdmin();
    }

    match /conversations/{conversationId} {
      allow read, write: if request.auth != null &&
                            request.auth.uid == resource.data.userId;
      allow create: if request.auth != null &&
                       request.auth.uid == request.resource.data.userId;

      match /messages/{messageId} {
        allow read, write: if request.auth != null &&
          request.auth.uid == get(/databases/$(database)/documents/conversations/$(conversationId)).data.userId;
      }
    }

    match /feedback/{feedbackId} {
      allow create: if request.auth != null;
      allow read, list: if isAdmin();
    }
  }
}
```

Clic en **Publicar**.

> El archivo `firestore.rules` en la raíz del proyecto contiene esta misma versión y sirve como fuente de verdad versionada.

---

## 3. Índices compuestos

Ir a la pestaña **Índices** dentro de Firestore → **Índices compuestos** → **Agregar índice**.

Crear los siguientes dos índices (uno a la vez):

### Índice 1 — Lista de conversaciones del usuario

| Campo        | ID de la colección |
| ------------ | ------------------ |
| `userId`     | `conversations`    |
| `updatedAt`  | Descendente        |

### Índice 2 — Panel admin: feedback filtrado por rating

| Campo       | ID de la colección |
| ----------- | ------------------ |
| `rating`    | `feedback`         |
| `createdAt` | Descendente        |

Cada índice tarda ~1 minuto en pasar de **Building** a **Enabled**.

> Los índices de un solo campo (`messages.createdAt`, `feedback.createdAt`, `users.createdAt`) los crea Firestore automáticamente — no hay que hacer nada. El archivo `firestore.indexes.json` en la raíz refleja la configuración versionada.

---

## 4. Credenciales del frontend (SDK cliente)

**Ruta:** Firebase Console → ⚙️ Configuración del proyecto → pestaña **General** → sección **Tus apps** → seleccionar la app web → **Configuración del SDK**.

Ahí aparecen todas las variables. Copiarlas al archivo `frontend/.env.local`:

| Variable en `.env.local`                    | Campo en Firebase Console |
| ------------------------------------------- | ------------------------- |
| `NEXT_PUBLIC_FIREBASE_API_KEY`              | `apiKey`                  |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`          | `authDomain`              |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID`           | `projectId`               |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET`       | `storageBucket`           |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID`  | `messagingSenderId`       |
| `NEXT_PUBLIC_FIREBASE_APP_ID`               | `appId`                   |

> Si no existe una app web todavía, crearla primero: en la misma página de Configuración del proyecto, clic en **Agregar app** → icono web (`</>`). No hace falta Firebase Hosting.

---

## 5. Service Account — credenciales del backend

El backend (FastAPI) usa Firebase Admin SDK para verificar tokens y leer/escribir Firestore. Necesita un archivo JSON con las credenciales de un Service Account.

### Generar el archivo JSON

1. Ir a ⚙️ **Configuración del proyecto → Cuentas de servicio**.
2. Clic en **Generar nueva clave privada**.
3. Confirmar → se descarga un archivo `.json`.
4. Guardarlo en la raíz del proyecto (ej. `firebase-service-account.json`). **No incluirlo en git** (ya está en `.gitignore`).

### Configurar la variable de entorno

En el archivo `.env` del proyecto (raíz), agregar:

```bash
FIREBASE_SERVICE_ACCOUNT_PATH=firebase-service-account.json
```

La ruta puede ser relativa a la raíz del proyecto o absoluta.

---

## 6. Asignar roles de administrador

No existe endpoint para esto — es deliberadamente manual para reducir la superficie de ataque.

1. Ir a **Firestore → Datos**.
2. Navegar a la colección `users` → documento del usuario (el ID es el UID de Firebase Auth).
3. Editar el campo `role` y cambiar su valor a `admin` o `super-admin`.

Los valores válidos son `user` (default), `admin` y `super-admin`.
