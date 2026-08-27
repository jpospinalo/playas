# ── Cluster ───────────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = local.name_prefix

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
}

# ── CloudWatch Log Groups ─────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${local.name_prefix}-app"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/${local.name_prefix}-frontend"
  retention_in_days = 14
}

# ── Task Definition: App (backend + postgres sidecar) ────────────────────────
# Postgres corre como sidecar en la misma tarea; se comunican por localhost.

resource "aws_ecs_task_definition" "app" {
  family                   = "${local.name_prefix}-app"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = data.aws_iam_role.lab.arn
  task_role_arn            = data.aws_iam_role.lab.arn

  volume {
    name = "postgres-data"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.postgres.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.postgres.id
        iam             = "ENABLED"
      }
    }
  }

  container_definitions = jsonencode([
    # ── Postgres ──────────────────────────────────────────────────────────────
    {
      name    = "postgres"
      image   = "postgres:16-alpine"
      # EFS no permite chown desde root; correr como postgres (uid 999) evita el intento
      user    = "999:999"
      command = ["sh", "-c", "rm -f /var/lib/postgresql/data/postmaster.pid && docker-entrypoint.sh postgres"]

      portMappings = [{
        containerPort = 5432
        protocol      = "tcp"
      }]

      healthCheck = {
        command     = ["CMD-SHELL", "pg_isready -U atlas -d atlas"]
        interval    = 10
        timeout     = 5
        retries     = 5
        startPeriod = 60
      }

      environment = [
        { name = "POSTGRES_DB",       value = "atlas" },
        { name = "POSTGRES_USER",     value = "atlas" },
        { name = "POSTGRES_PASSWORD", value = var.postgres_password }
      ]

      mountPoints = [{
        sourceVolume  = "postgres-data"
        containerPath = "/var/lib/postgresql/data"
        readOnly      = false
      }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "postgres"
        }
      }

      essential = true
    },
    # ── Backend ───────────────────────────────────────────────────────────────
    {
      name  = "backend"
      image = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"

      portMappings = [{
        containerPort = 8080
        protocol      = "tcp"
      }]

      environment = [
        # Postgres corre en localhost dentro de la misma tarea
        { name = "DATABASE_URL",             value = "postgresql+asyncpg://atlas:${var.postgres_password}@localhost:5432/atlas" },
        { name = "JWT_SECRET_KEY",           value = var.jwt_secret_key },
        { name = "JWT_ALGORITHM",            value = var.jwt_algorithm },
        { name = "JWT_EXPIRE_MINUTES",       value = tostring(var.jwt_expire_minutes) },
        { name = "OPENAI_API_KEY",           value = var.openai_api_key },
        { name = "OPENAI_MODEL",             value = var.openai_model },
        { name = "OPENROUTER_API_KEY",       value = var.openrouter_api_key },
        { name = "OPENROUTER_MODEL",         value = var.openrouter_model },
        { name = "GOOGLE_API_KEY",           value = var.google_api_key },
        { name = "GEMINI_MODEL",             value = var.gemini_model },
        { name = "CHROMA_HOST",              value = var.chroma_host },
        { name = "CHROMA_PORT",              value = tostring(var.chroma_port) },
        { name = "CHROMA_COLLECTION",        value = var.chroma_collection },
        { name = "OLLAMA_BASE_URL",          value = var.ollama_base_url },
        { name = "OLLAMA_EMBEDDING_MODEL",   value = var.ollama_embedding_model },
        { name = "OLLAMA_RERANKER_MODEL",    value = var.ollama_reranker_model },
        { name = "QUERY_ENRICHMENT_ENABLED", value = tostring(var.query_enrichment_enabled) },
        { name = "S3_BUCKET_NAME",           value = var.s3_bucket_name }
      ]

      dependsOn = [{
        containerName = "postgres"
        condition     = "HEALTHY"
      }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "backend"
        }
      }

      essential = true
    }
  ])
}

# ── Task Definition: Frontend ─────────────────────────────────────────────────

resource "aws_ecs_task_definition" "frontend" {
  family                   = "${local.name_prefix}-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = data.aws_iam_role.lab.arn
  task_role_arn            = data.aws_iam_role.lab.arn

  container_definitions = jsonencode([{
    name  = "frontend"
    image = "${aws_ecr_repository.frontend.repository_url}:${var.frontend_image_tag}"

    portMappings = [{
      containerPort = 3000
      protocol      = "tcp"
    }]

    environment = [
      { name = "NODE_ENV", value = "production" },
      { name = "PORT",     value = "3000" }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.frontend.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "frontend"
      }
    }

    essential = true
  }])
}

# ── ECS Service: App ──────────────────────────────────────────────────────────

resource "aws_ecs_service" "app" {
  name                    = "${local.name_prefix}-app"
  cluster                 = aws_ecs_cluster.main.id
  task_definition         = aws_ecs_task_definition.app.arn
  desired_count                      = 1
  launch_type                        = "FARGATE"
  enable_execute_command             = true
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8080
  }

  depends_on = [
    aws_lb_listener.http,
    aws_efs_mount_target.postgres
  ]
}

# ── ECS Service: Frontend ─────────────────────────────────────────────────────

resource "aws_ecs_service" "frontend" {
  name            = "${local.name_prefix}-frontend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.frontend.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 3000
  }

  depends_on = [aws_lb_listener.http]
}
