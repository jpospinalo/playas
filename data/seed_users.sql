-- Usuarios de prueba generados automáticamente (prefijos: usuario, usa).
-- Password en texto plano NO se guarda aquí; ver el archivo de credenciales.
INSERT INTO users (id, email, password_hash, display_name, role, created_at) VALUES
    ('dedfb3ec-7681-47f9-81dd-a6de9e9b2aaa', 'usuario1@atlas.local', '$2b$12$1OxMdKcp39.2JC9ehb/CxO4grvrlCh9ZYkuMEsrf0Xmpqwbsyp4fS', 'Usuario 1', 'user', '2026-07-03T20:20:34.566362+00:00'),
    ('2d2b624c-c881-4626-a4c2-54b5781932d3', 'usuario2@atlas.local', '$2b$12$xBKVjI1GD8BGVoqatUBXnONi4kFThsLEDdLPJU78gWgwOnvb7IuOy', 'Usuario 2', 'user', '2026-07-03T20:20:34.566362+00:00'),
    ('0f1629ca-9d6e-47bd-8c67-3e37fbc92cff', 'usuario3@atlas.local', '$2b$12$yvIK8AjqNK4WOC7lF2pc9OlITEPkk58Eul2knF8fkcW58zA9dgIAu', 'Usuario 3', 'user', '2026-07-03T20:20:34.566362+00:00'),
    ('11689575-d340-4a03-8ec2-c7753bab09bd', 'usuario4@atlas.local', '$2b$12$p.fcsFKr4BA3PCCclzWHYuYWbxeL8a9wyEDtZ41tqk9IQicargE7W', 'Usuario 4', 'user', '2026-07-03T20:20:34.566362+00:00'),
    ('fe56ab4a-fd11-4564-9110-d15d3d403555', 'usuario5@atlas.local', '$2b$12$H393AweOkIvaStvIC21OWucD0pBbHkA5paHhUICfWnKbZibIwIaJy', 'Usuario 5', 'user', '2026-07-03T20:20:34.566362+00:00'),
    ('797e62a9-0872-4fa5-ad4e-f4b0fabf7ca2', 'usa1@atlas.local', '$2b$12$B/jwSN1LsSlQto.lGMFGcuHeFnc4t99LfzJYcFj2trQOxJkwsgHPu', 'Usa 1', 'user', '2026-07-03T20:20:34.566362+00:00'),
    ('4e2999c3-637e-4c36-8a38-085521560f13', 'usa2@atlas.local', '$2b$12$yv2DMYmSI85clqMhDR8ODenRBrkAjpg/InIby9ZzAfiqQx7uGg1Ty', 'Usa 2', 'user', '2026-07-03T20:20:34.566362+00:00'),
    ('d09ab57d-9909-4522-95d4-fc6838b84478', 'usa3@atlas.local', '$2b$12$6w5GVbTnC5mxY7055lDEduIPTsJAyaet31H./AqsQ7prXpyTq/tXi', 'Usa 3', 'user', '2026-07-03T20:20:34.566362+00:00'),
    ('cfea398e-6011-4fe0-8708-a5f3818f9571', 'usa4@atlas.local', '$2b$12$rQZ8NX2IvzslzF/lL477OuWFkTowEsp7jIIl8vJhuGYLrGoSVwPiW', 'Usa 4', 'user', '2026-07-03T20:20:34.566362+00:00'),
    ('964b7358-1eb7-465f-9d28-e16419708dbc', 'usa5@atlas.local', '$2b$12$swl0NPovYcvknn/jc0OGAej3wjCV0tlWaxIqxN0G9n8LZcQBjrEOu', 'Usa 5', 'user', '2026-07-03T20:20:34.566362+00:00')
ON CONFLICT DO NOTHING;
