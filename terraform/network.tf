module "vpc" {
  source = "git::https://github.com/Smiley2507/terraform-aws-modules.git//modules/vpc?ref=main"

  name                 = "${var.project}-vpc"
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
}

module "igw" {
  source = "git::https://github.com/Smiley2507/terraform-aws-modules.git//modules/internet-gateway?ref=main"

  name   = "${var.project}-igw"
  vpc_id = module.vpc.vpc_id
}

module "public_subnet" {
  source = "git::https://github.com/Smiley2507/terraform-aws-modules.git//modules/subnet?ref=main"

  name                    = "${var.project}-public-subnet"
  vpc_id                  = module.vpc.vpc_id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true
}

module "public_route_table" {
  source = "git::https://github.com/Smiley2507/terraform-aws-modules.git//modules/route-table?ref=main"

  name       = "${var.project}-public-rt"
  vpc_id     = module.vpc.vpc_id
  subnet_ids = [module.public_subnet.subnet_id]

  routes = [
    {
      cidr_block = "0.0.0.0/0"
      gateway_id = module.igw.internet_gateway_id
    }
  ]
}
