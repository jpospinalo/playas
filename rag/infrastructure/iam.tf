# LabRole es el rol preexistente en AWS Academy con permisos para ECS, ECR y EFS
data "aws_iam_role" "lab" {
  name = "LabRole"
}
