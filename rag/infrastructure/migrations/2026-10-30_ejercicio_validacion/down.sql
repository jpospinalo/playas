-- Vuelta atrás
-- Generado por infrastructure/migrations/generar_sql.py a partir de
-- rag/backend/rag/api/models.py. No editar a mano: regenerar.
--
-- Solo borra las 14 tablas del ejercicio de validación (panel, cuentas,
-- evaluación, premios, aviso de datos). No toca users, conversations,
-- messages, feedback ni message_feedback.

-- OJO: borra los datos guardados en esas tablas (cuentas del ejercicio,
-- calificaciones, validaciones, premios). Sacar copia antes.
-- RESTRICT (no CASCADE): si algo inesperado depende de ellas, falla en
-- vez de borrar de más.

BEGIN;

DROP TABLE IF EXISTS evaluation_review RESTRICT;

DROP TABLE IF EXISTS evaluation_comment RESTRICT;

DROP TABLE IF EXISTS question_number RESTRICT;

DROP TABLE IF EXISTS question_evaluation RESTRICT;

DROP TABLE IF EXISTS question_assignment RESTRICT;

DROP TABLE IF EXISTS pertinence_review RESTRICT;

DROP TABLE IF EXISTS award_decision RESTRICT;

DROP TABLE IF EXISTS validator_profile RESTRICT;

DROP TABLE IF EXISTS privacy_consent RESTRICT;

DROP TABLE IF EXISTS practice_account RESTRICT;

DROP TABLE IF EXISTS exercise_profile RESTRICT;

DROP TABLE IF EXISTS account_status RESTRICT;

DROP TABLE IF EXISTS exercise_setting RESTRICT;

DROP TABLE IF EXISTS admin_audit RESTRICT;

COMMIT;
