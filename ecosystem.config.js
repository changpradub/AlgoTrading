module.exports = {
  apps: [
    {
      name: "algotrading-bot",
      script: "bot.py",
      // Use Python binary inside virtualenv
      interpreter: "./.venv/bin/python3",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      restart_delay: 5000,
      max_restarts: 15,
      min_uptime: "60s",
      env: {
        PYTHONUNBUFFERED: "1",
        NODE_ENV: "production",
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      error_file: "logs/pm2-error.log",
      out_file: "logs/pm2-out.log",
      merge_logs: true,
    },
  ],
};
