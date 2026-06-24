# ── ALB ──────────────────────────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb"
  description = "Public HTTP traffic to the ALB"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── App (backend + postgres sidecar) ─────────────────────────────────────────

resource "aws_security_group" "app" {
  name        = "${local.name_prefix}-app"
  description = "FastAPI backend traffic from ALB"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "FastAPI from ALB"
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── Frontend ──────────────────────────────────────────────────────────────────

resource "aws_security_group" "frontend" {
  name        = "${local.name_prefix}-frontend"
  description = "Next.js frontend traffic from ALB"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Next.js from ALB"
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── EFS ───────────────────────────────────────────────────────────────────────

resource "aws_security_group" "efs" {
  name        = "${local.name_prefix}-efs"
  description = "NFS mount for EFS from app task"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "NFS from app"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
