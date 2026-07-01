import argparse
import logging
import os

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [AWS_FLEET] %(levelname)s: %(message)s')
logger = logging.getLogger("AWS_FLEET")

load_dotenv()

# Configurações de Regiões para teste de Latência
TARGET_REGIONS = [
    "eu-west-1",      # Irlanda (mais provavel de ser proximo aos servidores da Deriv em Malta)
    "ap-northeast-1", # Toquio (proximo aos servidores Binance de Cripto)
    "us-east-1",      # Virginia (backbone geral AWS)
]

INSTANCE_TYPE = "t2.micro"  # Free Tier eligible (so gratis nos 1os 12 meses da conta, e so em 1 regiao por vez)
KEY_NAME = "megabrain-probe-key"
SG_NAME = "megabrain-probe-sg"
KEYS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aws_keys")

UBUNTU_OWNER_ID = "099720109477"  # Canonical
UBUNTU_NAME_FILTER = "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"


class AWSFleetManager:
    def __init__(self, regions=None):
        self.regions = regions or TARGET_REGIONS
        self.sessions = {}
        kwargs = {}
        if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
            kwargs = {
                "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
                "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
            }
            if os.getenv("AWS_SESSION_TOKEN"):
                kwargs["aws_session_token"] = os.getenv("AWS_SESSION_TOKEN")
        for region in self.regions:
            self.sessions[region] = boto3.Session(region_name=region, **kwargs)

    def check_credentials(self):
        """Pre-flight: falha rapido e com mensagem clara em vez de estourar fundo do create_instances."""
        try:
            sts = list(self.sessions.values())[0].client("sts")
            identity = sts.get_caller_identity()
            logger.info(f"✅ Credenciais OK -> conta AWS {identity['Account']} (arn={identity['Arn']})")
            return True
        except (NoCredentialsError, NoRegionError) as e:
            logger.error(f"❌ Sem credenciais AWS configuradas ({e}).")
            logger.error("   Configure via `aws configure`, ~/.aws/credentials, ou AWS_ACCESS_KEY_ID/"
                         "AWS_SECRET_ACCESS_KEY no .env deste projeto. Precisa de um IAM user/role com "
                         "permissao ec2:* (RunInstances, DescribeImages, CreateKeyPair, CreateSecurityGroup, "
                         "DescribeVpcs, CreateTags) e sts:GetCallerIdentity.")
            return False
        except ClientError as e:
            logger.error(f"❌ Credenciais presentes mas rejeitadas pela AWS: {e}")
            return False

    def _latest_ubuntu_ami(self, ec2_client):
        images = ec2_client.describe_images(
            Owners=[UBUNTU_OWNER_ID],
            Filters=[
                {"Name": "name", "Values": [UBUNTU_NAME_FILTER]},
                {"Name": "state", "Values": ["available"]},
                {"Name": "architecture", "Values": ["x86_64"]},
            ],
        )["Images"]
        if not images:
            raise RuntimeError("Nenhuma AMI Ubuntu 22.04 encontrada nesta regiao.")
        return sorted(images, key=lambda x: x["CreationDate"], reverse=True)[0]["ImageId"]

    def _ensure_key_pair(self, ec2_client, region, dry_run):
        try:
            ec2_client.describe_key_pairs(KeyNames=[KEY_NAME])
            return KEY_NAME
        except ClientError as e:
            if "InvalidKeyPair.NotFound" not in str(e):
                raise
        if dry_run:
            logger.info(f"[dry-run] {region}: key pair '{KEY_NAME}' nao existe ainda; seria criada em modo --real.")
            return KEY_NAME
        kp = ec2_client.create_key_pair(KeyName=KEY_NAME)
        os.makedirs(KEYS_DIR, exist_ok=True)
        pem_path = os.path.join(KEYS_DIR, f"{KEY_NAME}_{region}.pem")
        with open(pem_path, "w") as f:
            f.write(kp["KeyMaterial"])
        os.chmod(pem_path, 0o400)
        logger.info(f"🔑 Key pair criada em {region}, chave privada salva em {pem_path}")
        return KEY_NAME

    def _ensure_security_group(self, ec2_client, region, dry_run):
        try:
            resp = ec2_client.describe_security_groups(GroupNames=[SG_NAME])
            return resp["SecurityGroups"][0]["GroupId"]
        except ClientError as e:
            if "InvalidGroup.NotFound" not in str(e):
                raise
        if dry_run:
            logger.info(f"[dry-run] {region}: security group '{SG_NAME}' nao existe ainda; "
                        f"seria criado (SSH inbound) em modo --real.")
            return None
        vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
        if not vpcs:
            raise RuntimeError("Sem VPC default nesta regiao; crie uma VPC ou passe SecurityGroupId manualmente.")
        sg = ec2_client.create_security_group(
            GroupName=SG_NAME, Description="Mega Brain latency probes (SSH inbound)", VpcId=vpcs[0]["VpcId"],
        )
        sg_id = sg["GroupId"]
        ec2_client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                             "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH - restrinja ao seu IP"}]}],
        )
        logger.warning(f"🔓 Security group {SG_NAME} criado com SSH aberto para 0.0.0.0/0 -- "
                        f"restrinja ao seu IP manualmente no console AWS depois.")
        return sg_id

    def provision_latency_probes(self, dry_run=True):
        """Lanca instancias micro nas regioes alvo para medir ping contra Deriv/Binance.

        dry_run=True (padrao) so valida credenciais/permissoes via DryRun=True da API (nao cria nada,
        nao gera custo). dry_run=False efetivamente cria as instancias (custo real fora do Free Tier).
        """
        if not self.check_credentials():
            return {}

        instances = {}
        mode = "DRY-RUN (validacao, sem custo)" if dry_run else "REAL (vai gerar instancias cobraveis)"
        logger.info(f"🚀 Provisionamento da Frota de Testes de Latencia -- modo: {mode}")

        for region, session in self.sessions.items():
            ec2_client = session.client("ec2")
            ec2_resource = session.resource("ec2")
            try:
                ami_id = self._latest_ubuntu_ami(ec2_client)
                key_name = self._ensure_key_pair(ec2_client, region, dry_run)
                sg_id = self._ensure_security_group(ec2_client, region, dry_run)
                logger.info(f"{region}: AMI={ami_id} key={key_name} sg={sg_id}")

                if dry_run and sg_id is None:
                    logger.info(f"✅ {region}: dry-run OK (credenciais/AMI validos; SG/key ainda nao existem, "
                                f"serao criados em modo --real antes do RunInstances).")
                    continue

                new_instances = ec2_resource.create_instances(
                    ImageId=ami_id,
                    MinCount=1,
                    MaxCount=1,
                    InstanceType=INSTANCE_TYPE,
                    KeyName=key_name,
                    SecurityGroupIds=[sg_id],
                    DryRun=dry_run,
                    TagSpecifications=[{
                        "ResourceType": "instance",
                        "Tags": [{"Key": "Name", "Value": f"MegaBrain-Probe-{region}"}],
                    }],
                )
                instances[region] = new_instances[0].id
                logger.info(f"✅ Instância {new_instances[0].id} criada em {region}.")
            except ClientError as e:
                if "DryRunOperation" in str(e):
                    logger.info(f"✅ {region}: dry-run OK (credenciais/permissoes validas, nada foi criado).")
                else:
                    logger.error(f"❌ Erro ao subir instância em {region}: {e}")
            except Exception as e:
                logger.error(f"❌ Erro ao subir instância em {region}: {e}")

        return instances


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Provisiona (ou valida, via --dry-run) sondas EC2 de latencia.")
    ap.add_argument("--real", action="store_true", help="Provisiona de verdade (custo real). Sem isso, roda em dry-run.")
    ap.add_argument("--regions", default=",".join(TARGET_REGIONS))
    args = ap.parse_args()

    fleet = AWSFleetManager(regions=[r.strip() for r in args.regions.split(",") if r.strip()])
    fleet.provision_latency_probes(dry_run=not args.real)
    if not args.real:
        logger.info("Modo dry-run (padrao). Use --real para provisionar de fato (gera custo fora do Free Tier).")
