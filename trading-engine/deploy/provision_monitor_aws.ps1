# Provisiona uma t3.micro (Ubuntu 22.04) em ap-northeast-1 p/ rodar o
# synthetic_anomaly_monitor 24/7. Usa o perfil ja configurado (aws configure)
# -> precisa de AmazonEC2FullAccess. Salva estado em ~/.aws/anomaly-monitor.state.json.
$ErrorActionPreference = "Stop"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$env:AWS_PAGER = ""

$REGION  = "ap-northeast-1"
$KEYNAME = "anomaly-monitor"
$SGNAME  = "anomaly-monitor-sg"
$ITYPE   = "t3.micro"
$awsdir  = Join-Path $env:USERPROFILE ".aws"
$KEYPATH = Join-Path $awsdir "$KEYNAME.pem"
$STATE   = Join-Path $awsdir "anomaly-monitor.state.json"

$ident = aws sts get-caller-identity --output json | ConvertFrom-Json
Write-Host ("== Conta {0} ({1})" -f $ident.Account, $ident.Arn) -ForegroundColor Cyan

Write-Host "== 1/4 AMI Ubuntu 22.04 (Canonical, describe-images) =="
$AMI = aws ec2 describe-images --region $REGION --owners 099720109477 `
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" "Name=state,Values=available" `
  --query "sort_by(Images,&CreationDate)[-1].ImageId" --output text
if (-not $AMI -or $AMI -eq "None") { throw "Falha ao obter AMI (precisa de ec2:DescribeImages)." }
Write-Host "  AMI: $AMI"

Write-Host "== 2/4 Key pair =="
aws ec2 delete-key-pair --region $REGION --key-name $KEYNAME 2>$null | Out-Null
if (Test-Path $KEYPATH) { Remove-Item $KEYPATH -Force }
$km = aws ec2 create-key-pair --region $REGION --key-name $KEYNAME --query KeyMaterial --output text
if (-not $km) { throw "Falha ao criar o key pair." }
[IO.File]::WriteAllText($KEYPATH, (($km -join "`n").TrimEnd() + "`n"))
icacls $KEYPATH /inheritance:r /grant:r "$($env:USERNAME):R" | Out-Null
Write-Host "  Chave privada: $KEYPATH"

Write-Host "== 3/4 Security group (SSH so do seu IP) =="
$MYIP = (Invoke-WebRequest -UseBasicParsing https://checkip.amazonaws.com).Content.Trim()
$SG = aws ec2 describe-security-groups --region $REGION --filters "Name=group-name,Values=$SGNAME" --query "SecurityGroups[0].GroupId" --output text 2>$null
if (-not $SG -or $SG -eq "None") {
  $SG = aws ec2 create-security-group --region $REGION --group-name $SGNAME --description "anomaly monitor" --query GroupId --output text
}
if (-not $SG -or $SG -eq "None") { throw "Falha ao obter/criar o security group." }
aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG --protocol tcp --port 22 --cidr "$MYIP/32" 2>$null | Out-Null
Write-Host "  SG: $SG | SSH liberado p/ $MYIP/32"

Write-Host "== 4/4 run-instances ($ITYPE) =="
$IID = aws ec2 run-instances --region $REGION --image-id $AMI --instance-type $ITYPE --key-name $KEYNAME --security-group-ids $SG --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=anomaly-monitor}]" --query "Instances[0].InstanceId" --output text
if (-not $IID -or $IID -eq "None") { throw "Falha no run-instances." }
Write-Host "  Instancia: $IID (aguardando running...)"
aws ec2 wait instance-running --region $REGION --instance-ids $IID
$IP = aws ec2 describe-instances --region $REGION --instance-ids $IID --query "Reservations[0].Instances[0].PublicIpAddress" --output text
if (-not $IP -or $IP -eq "None") { throw "Instancia sem IP publico." }

@{ region = $REGION; instanceId = $IID; securityGroupId = $SG; keyName = $KEYNAME; keyPath = $KEYPATH; ip = $IP; myip = $MYIP } | ConvertTo-Json | Set-Content -Encoding ascii $STATE

Write-Host ""
Write-Host "== PRONTO ==" -ForegroundColor Green
Write-Host "  InstanceId : $IID"
Write-Host "  IP publico : $IP"
Write-Host "  SG         : $SG"
Write-Host "  Estado     : $STATE"
Write-Host "  Custo t3.micro Toquio ~US`$0.017/h (~US`$12/mes 24/7)"
Write-Host "  SSH leva ~30-60s p/ aceitar. Depois rode deploy_monitor_aws.ps1"
