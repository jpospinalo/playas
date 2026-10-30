-- Migración de subida
-- Generado por infrastructure/migrations/generar_sql.py a partir de
-- rag/backend/rag/api/models.py. No editar a mano: regenerar.
--
-- Solo crea las 14 tablas del ejercicio de validación (panel, cuentas,
-- evaluación, premios, aviso de datos). No toca users, conversations,
-- messages, feedback ni message_feedback.

-- Idempotente: usa IF NOT EXISTS, se puede correr dos veces.

BEGIN;

CREATE TABLE IF NOT EXISTS admin_audit (
	id VARCHAR NOT NULL, 
	actor_id VARCHAR NOT NULL, 
	accion VARCHAR NOT NULL, 
	objetivo_id VARCHAR, 
	detalle JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_admin_audit_actor_id ON admin_audit (actor_id);

CREATE INDEX IF NOT EXISTS ix_admin_audit_created_at ON admin_audit (created_at);

CREATE TABLE IF NOT EXISTS exercise_setting (
	clave VARCHAR NOT NULL, 
	valor VARCHAR NOT NULL, 
	updated_by VARCHAR, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (clave)
);

CREATE TABLE IF NOT EXISTS account_status (
	user_id VARCHAR NOT NULL, 
	activa BOOLEAN NOT NULL, 
	cambiada_por VARCHAR, 
	cambiada_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS exercise_profile (
	user_id VARCHAR NOT NULL, 
	codigo VARCHAR, 
	tipo_playa INTEGER, 
	sede VARCHAR, 
	organizacion VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_exercise_profile_codigo ON exercise_profile (codigo);

CREATE TABLE IF NOT EXISTS practice_account (
	user_id VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS privacy_consent (
	user_id VARCHAR NOT NULL, 
	version VARCHAR NOT NULL, 
	aceptada_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS validator_profile (
	user_id VARCHAR NOT NULL, 
	tipo VARCHAR NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS award_decision (
	nivel VARCHAR(1) NOT NULL, 
	message_id VARCHAR NOT NULL, 
	decidido_por VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (nivel), 
	FOREIGN KEY(message_id) REFERENCES messages (id), 
	FOREIGN KEY(decidido_por) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS pertinence_review (
	message_id VARCHAR NOT NULL, 
	validador_id VARCHAR NOT NULL, 
	pertinente BOOLEAN NOT NULL, 
	comentario TEXT, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (message_id), 
	FOREIGN KEY(message_id) REFERENCES messages (id), 
	FOREIGN KEY(validador_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS question_assignment (
	message_id VARCHAR NOT NULL, 
	sede VARCHAR NOT NULL, 
	evaluador_id VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	reasignada_de VARCHAR, 
	PRIMARY KEY (message_id, sede), 
	FOREIGN KEY(message_id) REFERENCES messages (id), 
	FOREIGN KEY(evaluador_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_question_assignment_evaluador_id ON question_assignment (evaluador_id);

CREATE TABLE IF NOT EXISTS question_evaluation (
	id VARCHAR NOT NULL, 
	message_id VARCHAR NOT NULL, 
	evaluador_id VARCHAR NOT NULL, 
	sede VARCHAR, 
	f1 INTEGER NOT NULL, 
	f2 INTEGER NOT NULL, 
	f3 INTEGER NOT NULL, 
	ct VARCHAR(1) NOT NULL, 
	cv INTEGER NOT NULL, 
	total INTEGER NOT NULL, 
	valida BOOLEAN NOT NULL, 
	observaciones TEXT, 
	es_final BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (message_id, evaluador_id, es_final), 
	FOREIGN KEY(message_id) REFERENCES messages (id), 
	FOREIGN KEY(evaluador_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_question_evaluation_message_id ON question_evaluation (message_id);

CREATE TABLE IF NOT EXISTS question_number (
	message_id VARCHAR NOT NULL, 
	numero INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (message_id), 
	FOREIGN KEY(message_id) REFERENCES messages (id), 
	UNIQUE (numero)
);

CREATE TABLE IF NOT EXISTS evaluation_comment (
	id VARCHAR NOT NULL, 
	evaluation_id VARCHAR NOT NULL, 
	autor_id VARCHAR NOT NULL, 
	tipo VARCHAR NOT NULL, 
	texto TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(evaluation_id) REFERENCES question_evaluation (id), 
	FOREIGN KEY(autor_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_evaluation_comment_evaluation_id ON evaluation_comment (evaluation_id);

CREATE TABLE IF NOT EXISTS evaluation_review (
	id VARCHAR NOT NULL, 
	evaluation_id VARCHAR NOT NULL, 
	validador_id VARCHAR NOT NULL, 
	de_acuerdo BOOLEAN NOT NULL, 
	comentario TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(evaluation_id) REFERENCES question_evaluation (id), 
	FOREIGN KEY(validador_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_evaluation_review_evaluation_id ON evaluation_review (evaluation_id);

COMMIT;
