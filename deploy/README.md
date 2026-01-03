# FavvoCoaster Lambda Deployment

# 

# Quick deployment for personal use. Not production-grade.

# 

# Prerequisites:

# - AWS CLI configured (aws configure)

# - Terraform >= 1.0

# - Python 3.12

# - Spotify app created at https://developer.spotify.com/dashboard

## First-time setup

```bash
# 1. Export Spotify creds
export SPOTIFY_CLIENT_ID="your_client_id"
export SPOTIFY_CLIENT_SECRET="your_client_secret"
export AWS_REGION="eu-north-1"  # or your preferred region

# 2. Build Lambda package
chmod +x deploy/build.sh
./deploy/build.sh

# 3. Deploy infrastructure
cd deploy
terraform init
terraform apply \
    -var="spotify_client_id=$SPOTIFY_CLIENT_ID" \
    -var="spotify_client_secret=$SPOTIFY_CLIENT_SECRET" \
    -var="aws_region=$AWS_REGION"

# 4. Bootstrap OAuth token (ONE TIME - opens browser)
export SSM_TOKEN_PARAM="/favvocoaster/spotify_token"
python -m favvocoaster.bootstrap_token

# 5. Test it works
aws lambda invoke --function-name favvocoaster /dev/stdout
```

## How it works

1. **EventBridge** triggers Lambda every minute (configurable)
2. **Lambda** polls Spotify for new liked songs
3. OAuth tokens are stored in **SSM Parameter Store** (auto-refreshed)
4. If you're playing music, matching tracks get queued

## Updating code

```bash
./deploy/build.sh
cd deploy
terraform apply -var="spotify_client_id=$SPOTIFY_CLIENT_ID" -var="spotify_client_secret=$SPOTIFY_CLIENT_SECRET"
```

## Viewing logs

```bash
# Tail logs
aws logs tail /aws/lambda/favvocoaster --follow

# Recent logs
aws logs tail /aws/lambda/favvocoaster --since 1h
```

## Manual invoke

```bash
aws lambda invoke --function-name favvocoaster /dev/stdout
```

## Adjusting schedule

Edit `schedule_rate` in terraform:

- `rate(1 minute)` - every minute
- `rate(5 minutes)` - every 5 min
- `cron(0/15 * * * ? *)` - every 15 min

## Costs

Basically free for personal use:

- Lambda: ~43k invocations/month at 1/min = well within free tier
- SSM: 1 parameter = free
- CloudWatch Logs: minimal, 7 day retention

## Destroying

```bash
cd deploy
terraform destroy -var="spotify_client_id=x" -var="spotify_client_secret=x"
```

## Troubleshooting

**"No active playback"** - Lambda can only queue if Spotify is actively playing
on a device

**Token errors** - Re-run bootstrap: `python -m favvocoaster.bootstrap_token`

**Check SSM token exists:**

```bash
aws ssm get-parameter --name /favvocoaster/spotify_token --with-decryption
```
