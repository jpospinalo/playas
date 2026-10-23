cat << 'EOF' > components/AuthForm.jsx
import React, { useState } from 'react';

export default function AuthForm() {
  const [isRegistering, setIsRegistering] = useState(false);
  const [formData, setFormData] = useState({
    nombre_completo: '',
    correo: '',
    cedula: '',
    telefono: '',
    password: ''
  });
  const [message, setMessage] = useState(null);

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMessage(null);

    const endpoint = isRegistering ? '/api/v1/auth/register' : '/api/v1/auth/login';
    
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Ocurrió un error en la solicitud.');
      }

      setMessage({ type: 'success', text: isRegistering ? 'Registro exitoso. Ya puedes iniciar sesión.' : 'Sesión iniciada.' });
      if (isRegistering) setIsRegistering(false);
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
    }
  };

  return (
    <div style={{ maxWidth: '400px', margin: '40px auto', padding: '20px', border: '1px solid #ccc', borderRadius: '8px' }}>
      <h2>{isRegistering ? 'Crear cuenta en ATLAS' : 'Iniciar Sesión'}</h2>
      
      {message && (
        <div style={{ padding: '10px', marginBottom: '10px', backgroundColor: message.type === 'error' ? '#ffdddd' : '#ddffdd' }}>
          {message.text}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        {isRegistering && (
          <>
            <div>
              <label>Nombre Completo</label>
              <input type="text" name="nombre_completo" required onChange={handleChange} style={{ width: '100%', marginBottom: '10px' }} />
            </div>
            <div>
              <label>Cédula</label>
              <input type="text" name="cedula" required onChange={handleChange} style={{ width: '100%', marginBottom: '10px' }} />
            </div>
            <div>
              <label>Teléfono</label>
              <input type="tel" name="telefono" required onChange={handleChange} style={{ width: '100%', marginBottom: '10px' }} />
            </div>
          </>
        )}

        <div>
          <label>Correo Electrónico</label>
          <input type="email" name="correo" required onChange={handleChange} style={{ width: '100%', marginBottom: '10px' }} />
        </div>

        <div>
          <label>Contraseña</label>
          <input type="password" name="password" required onChange={handleChange} style={{ width: '100%', marginBottom: '10px' }} />
        </div>

        <button type="submit" style={{ width: '100%', padding: '10px', backgroundColor: '#0070f3', color: '#fff', border: 'none', borderRadius: '4px' }}>
          {isRegistering ? 'Registrarse' : 'Ingresar'}
        </button>
      </form>

      <p style={{ marginTop: '15px', textAlign: 'center' }}>
        {isRegistering ? '¿Ya tienes una cuenta?' : '¿No tienes cuenta?'}
        <button 
          type="button"
          onClick={() => setIsRegistering(!isRegistering)} 
          style={{ background: 'none', border: 'none', color: '#0070f3', cursor: 'pointer', textDecoration: 'underline', marginLeft: '5px' }}
        >
          {isRegistering ? 'Inicia sesión aquí' : 'Regístrate aquí'}
        </button>
      </p>
    </div>
  );
}
EOF
