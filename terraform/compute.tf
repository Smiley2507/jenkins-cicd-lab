module "key_pair" {
  source = "git::https://github.com/Smiley2507/terraform-aws-modules.git//modules/key-pair?ref=main"

  key_name              = "${var.project}-key"
  generate_key          = true
  rsa_bits              = 4096
  save_private_key_path = var.private_key_path
}

module "jenkins_server" {
  source = "git::https://github.com/Smiley2507/terraform-aws-modules.git//modules/ec2-instance?ref=main"

  name                        = "${var.project}-jenkins-server"
  instance_type               = var.jenkins_instance_type
  subnet_id                   = module.public_subnet.subnet_id
  vpc_security_group_ids      = [module.jenkins_sg.security_group_id]
  key_name                    = module.key_pair.key_name
  associate_public_ip_address = true
  root_volume_size            = var.jenkins_root_volume_size
  ami_name_filter             = var.ami_name_filter
  ami_owner                   = "amazon"
  iam_instance_profile = aws_iam_instance_profile.ec2_observability.name

  tags = {
    Role = "jenkins"
  }
}

module "app_server" {
  source = "git::https://github.com/Smiley2507/terraform-aws-modules.git//modules/ec2-instance?ref=main"

  name                        = "${var.project}-app-server"
  instance_type               = var.app_instance_type
  subnet_id                   = module.public_subnet.subnet_id
  vpc_security_group_ids      = [module.app_sg.security_group_id]
  key_name                    = module.key_pair.key_name
  associate_public_ip_address = true
  root_volume_size            = var.app_root_volume_size
  ami_name_filter             = var.ami_name_filter
  ami_owner                   = "amazon"

  iam_instance_profile = aws_iam_instance_profile.ec2_observability.name

  tags = {
    Role = "app"
  }
}