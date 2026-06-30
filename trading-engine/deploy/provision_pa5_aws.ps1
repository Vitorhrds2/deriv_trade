# Provisiona a VM do coletor PA5 (Polymarket Up/Down x Binance) em AWS.
# Sem segredos no arquivo: usa o perfil ja configurado no `aws configure`.
# Cria: key pair + security group (SSH so do seu IP) + topico SNS (email no fim) +
#       IAM role/instance-profile com sns:Publish + a instancia EC2.
# Salva o estado em ~/.aws/pa5-collector.state.json para deploy/teardown.
#
# Uso:
#   .\deploy\provision_pa5_aws.ps1 -Email voce@exemplo.com
#   .\deploy\provision_pa5_aws.ps1 -Email voce@exemplo.com -Region ap-northeast-1 -InstanceType t3.micro
param(
  [Parameter(Mandatory = $true)][string]$Email,
  [string]$Region = "us-east-1",
  [string]$InstanceType = "t3.micro"
)
$ErrorActionPreference = "Stop"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")

$KEYNAME = "pa5-collector"
$SGNAME  = "pa5-collector-sg"
$ROLE    = "pa5-collector-role"
$PROFILE = "pa5-collector-profile"
$TOPIC   = "pa5-collector-done"
$awsdir  = Join-Path $env:USERPROFILE ".aws"
$KEYPATH = Join-Path $awsdir "$KEYNAME.pem"
$STATE   = Join-Path $awsdir "pa5-collector.state.json"

Write-Host "== Conta AWS (CONFIRME que e a sua) ==" -ForegroundColor Cyan
$ident = aws sts get-caller-identity --output json | ConvertFrom-Json
Write-Host ("  Account {0}  ({1})  Region {2}" -f $ident.Account, $ident.Arn, $Region)
Write-Host ("  Email de notificacao: {0}" -f $Email)

Write-Host "== 1/6. AMI Ubuntu 22.04 (owner Canonical) =="
$AMI = aws ec2 describe-images --region $Region --owners 099720109477 --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" "Name=state,Values=available" --query "sort_by(Images, &CreationDate)[-1].ImageId" --output text
if (-not $AMI -or $AMI -eq "None") { throw "Falha ao obter a AMI." }
Write-Host "  AMI: $AMI"

Write-Host "== 2/6. Key pair =="
aws ec2 delete-key-pair --region $Region --key-name $KEYNAME 2>$null | Out-Null
if (Test-Path $KEYPATH) { Remove-Item $KEYPATH -Force }
$km = aws ec2 create-key-pair --region $Region --key-name $KEYNAME --query KeyMaterial --output text
if (-not $km) { throw "Falha ao criar o key pair." }
[IO.File]::WriteAllText($KEYPATH, (($km -join "`n").TrimEnd() + "`n"))
icacls $KEYPATH /inheritance:r /grant:r "$($env:USERNAME):R" | Out-Null
Write-Host "  Chave em $KEYPATH"

Write-Host "== 3/6. Security group + SSH so do seu IP =="
$MYIP = (Invoke-WebRequest -UseBasicParsing https://checkip.amazonaws.com).Content.Trim()
$SG = aws ec2 describe-security-groups --region $Region --filters "Name=group-name,Values=$SGNAME" --query "SecurityGroups[0].GroupId" --output text 2>$null
if (-not $SG -or $SG -eq "None") {
  $SG = aws ec2 create-security-group --region $Region --group-name $SGNAME --description "PA5 collector" --query GroupId --output text
}
aws ec2 authorize-security-group-ingress --region $Region --group-id $SG --protocol tcp --port 22 --cidr "$MYIP/32" 2>$null | Out-Null
Write-Host "  SG: $SG | SSH p/ $MYIP/32"

Write-Host "== 4/6. SNS topic + assinatura por email =="
$TOPIC_ARN = aws sns create-topic --region $Region --name $TOPIC --query TopicArn --output text
aws sns subscribe --region $Region --topic-arn $TOPIC_ARN --protocol email --notification-endpoint $Email | Out-Null
Write-Host "  Topic: $TOPIC_ARN" -ForegroundColor Green
Write-Host "  >>> CONFIRME a assinatura no email '$Email' (link 'Confirm subscription') ANTES das 48h." -ForegroundColor Yellow

Write-Host "== 5/6. IAM role + instance profile (sns:Publish) =="
$trust = Join-Path $awsdir "pa5-trust.json"
@'
{ "Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}
'@ | Set-Content -Encoding ascii $trust
aws iam create-role --role-name $ROLE --assume-role-policy-document "file://$trust" 2>$null | Out-Null
$perm = Join-Path $awsdir "pa5-perm.json"
@"
{ "Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"sns:Publish","Resource":"$TOPIC_ARN"}]}
"@ | Set-Content -Encoding ascii $perm
aws iam put-role-policy --role-name $ROLE --policy-name pa5-sns-publish --policy-document "file://$perm" | Out-Null
aws iam create-instance-profile --instance-profile-name $PROFILE 2>$null | Out-Null
aws iam add-role-to-instance-profile --instance-profile-name $PROFILE --role-name $ROLE 2>$null | Out-Null
Write-Host "  Role/Profile prontos. Aguardando propagacao do IAM (20s)..."
Start-Sleep -Seconds 20

Write-Host "== 6/6. Subindo a instancia ($InstanceType) =="
$IID = aws ec2 run-instances --region $Region --image-id $AMI --instance-type $InstanceType --key-name $KEYNAME --security-group-ids $SG --iam-instance-profile "Name=$PROFILE" --instance-initiated-shutdown-behavior stop --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=pa5-collector}]" --query "Instances[0].InstanceId" --output text
if (-not $IID -or $IID -eq "None") { throw "Falha ao subir a instancia (IAM ainda propagando? tente de novo)." }
aws ec2 wait instance-running --region $Region --instance-ids $IID
$IP = aws ec2 describe-instances --region $Region --instance-ids $IID --query "Reservations[0].Instances[0].PublicIpAddress" --output text

@{ region = $Region; instanceId = $IID; securityGroupId = $SG; keyName = $KEYNAME; keyPath = $KEYPATH;
   ip = $IP; myip = $MYIP; topicArn = $TOPIC_ARN; roleName = $ROLE; profileName = $PROFILE; email = $Email
} | ConvertTo-Json | Set-Content -Encoding ascii $STATE

Write-Host ""
Write-Host "== PRONTO ==" -ForegroundColor Green
Write-Host "  InstanceId : $IID"
Write-Host "  IP publico : $IP"
Write-Host "  SNS topic  : $TOPIC_ARN"
Write-Host "  Estado     : $STATE"
Write-Host "  Custo $InstanceType ~US`$0.01/h -> 48h ~US`$0.50 + EBS"
Write-Host "  Proximo: confirme o email do SNS e rode  .\deploy\deploy_pa5_aws.ps1  (SSH pode levar ~30-60s)"
