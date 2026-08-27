# IAM role letting both instances ship logs to CloudWatch.
#
# This replaces the alternative of putting AWS access keys on the servers.
# An instance profile issues short-lived credentials through the instance
# metadata service, so there is no long-lived secret anywhere on disk — which
# is both simpler and materially safer.

resource "aws_iam_role" "ec2_observability" {
  name = "${var.project}-ec2-observability"

  # Who may assume this role: the EC2 service, on behalf of instances it
  # attaches the matching instance profile to.
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

# Least privilege: only what the Docker awslogs driver and the CloudWatch agent
# actually call. Deliberately not CloudWatchAgentServerPolicy, which is broader.
resource "aws_iam_role_policy" "cloudwatch_logs" {
  name = "${var.project}-cloudwatch-logs"
  role = aws_iam_role.ec2_observability.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
          "logs:DescribeLogGroups",
          "logs:PutRetentionPolicy",
        ]
        Resource = "arn:aws:logs:${var.region}:*:log-group:*"
      },
    ]
  })
}

# Lets you open a shell through Session Manager without SSH or an open port 22.
# Optional, but it costs nothing and is a good answer to "how would you tighten
# SSH access?".
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.ec2_observability.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# The bridge between an IAM role and an EC2 instance.
resource "aws_iam_instance_profile" "ec2_observability" {
  name = "${var.project}-ec2-observability"
  role = aws_iam_role.ec2_observability.name
}