Deploy current changes to the EC2 server.

```bash
cd /Users/shashankreddyganta/Documents/btc-ai-agent && ./deploy/deploy.sh
```

This rsyncs the project to EC2 and restarts the systemd service.
After deploying, verify the service is running at https://btc.gshashank.com
