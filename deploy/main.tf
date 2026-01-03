# FavvoCoaster Lambda Deployment
#
# Quick & dirty Terraform for deploying to AWS Lambda.
# Presumes you have AWS creds configured and Terraform installed.
#
# Usage:
#   cd deploy/
#   terraform init
#   terraform apply -var="spotify_client_id=xxx" -var="spotify_client_secret=yyy"

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# -----------------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------------

variable "aws_region" {
  default = "eu-north-1"
}

variable "spotify_client_id" {
  type      = string
  sensitive = true
}

variable "spotify_client_secret" {
  type      = string
  sensitive = true
}

variable "schedule_rate" {
  description = "How often to run (EventBridge rate expression)"
  default     = "rate(1 minute)"
}

variable "ssm_token_param" {
  default = "/favvocoaster/spotify_token"
}

# -----------------------------------------------------------------------------
# SSM Parameter for Spotify token (created empty, bootstrap script fills it)
# -----------------------------------------------------------------------------

resource "aws_ssm_parameter" "spotify_token" {
  name  = var.ssm_token_param
  type  = "SecureString"
  value = "{}"  # Placeholder - bootstrap_token.py will overwrite

  lifecycle {
    ignore_changes = [value]  # Don't overwrite token on subsequent applies
  }

  tags = {
    App = "favvocoaster"
  }
}

# -----------------------------------------------------------------------------
# IAM Role for Lambda
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda" {
  name = "favvocoaster-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = {
    App = "favvocoaster"
  }
}

resource "aws_iam_role_policy" "lambda" {
  name = "favvocoaster-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:PutParameter"
        ]
        Resource = aws_ssm_parameter.spotify_token.arn
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "favvocoaster" {
  filename         = "${path.module}/lambda.zip"
  function_name    = "favvocoaster"
  role             = aws_iam_role.lambda.arn
  handler          = "favvocoaster.lambda_handler.handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256
  source_code_hash = filebase64sha256("${path.module}/lambda.zip")

  environment {
    variables = {
      SPOTIFY_CLIENT_ID           = var.spotify_client_id
      SPOTIFY_CLIENT_SECRET       = var.spotify_client_secret
      SSM_TOKEN_PARAM             = var.ssm_token_param
      SCRAPE_MIN_ARTISTS          = "2"
      SCRAPE_TOP_TRACKS_LIMIT     = "1"
      SCRAPE_SKIP_KNOWN_ARTISTS   = "true"
      SCRAPE_KNOWN_ARTISTS_SCAN_LIMIT = "500"
    }
  }

  tags = {
    App = "favvocoaster"
  }
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group (explicit so we can set retention)
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.favvocoaster.function_name}"
  retention_in_days = 7

  tags = {
    App = "favvocoaster"
  }
}

# -----------------------------------------------------------------------------
# EventBridge Schedule (triggers Lambda)
# -----------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "favvocoaster-schedule"
  description         = "Trigger FavvoCoaster Lambda on schedule"
  schedule_expression = var.schedule_rate

  tags = {
    App = "favvocoaster"
  }
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "favvocoaster-lambda"
  arn       = aws_lambda_function.favvocoaster.arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.favvocoaster.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "lambda_function_name" {
  value = aws_lambda_function.favvocoaster.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.favvocoaster.arn
}

output "ssm_token_parameter" {
  value = aws_ssm_parameter.spotify_token.name
}

output "log_group" {
  value = aws_cloudwatch_log_group.lambda.name
}
