# คู่มือการติดตั้งและ Deploy บน Oracle Cloud Always Free (Ubuntu VPS)

เอกสารนี้รวบรวมขั้นตอนการนำ **Personal Algo-Trading Bot** ขึ้นรันบนเซิร์ฟเวอร์ **Oracle Cloud Always Free (Ubuntu 22.04 / 24.04 LTS)** อย่างเป็นระบบ ครอบคลุมตั้งแต่การตั้งค่า Environment, PostgreSQL, PM2, และการทดสอบเชื่อมต่อจริง

---

## 📋 สิ่งที่ต้องเตรียมก่อนเริ่ม
1. **IP Address ของเซิร์ฟเวอร์ VPS** (Public IP จาก Oracle Cloud Console)
2. **SSH Private Key** (`.key` หรือ `.pem` ที่ดาวน์โหลดมาจาก Oracle Cloud)
3. **API Keys ที่จำเป็นสำหรับใส่ใน `.env`:**
   - Alpaca Paper API Key & Secret Key
   - Telegram Bot Token & Chat ID
   - OpenRouter API Key (สำหรับ AI Gatekeeper Gemini 3.8 Flash)

---

## 🚀 ขั้นตอนที่ 1: Push โค้ดล่าสุดขึ้น GitHub (ทำบนเครื่อง Local)

เปิด Terminal บนเครื่องของคุณและรันคำสั่ง:
```bash
git push -u origin develop
```

---

## 🖥️ ขั้นตอนที่ 2: SSH เข้าสู่ Oracle Cloud VPS

เปิด Terminal หรือ PowerShell แล้วรันคำสั่ง SSH:
```bash
# ตัวอย่าง: ปรับ path ไปยัง key file และ IP ของคุณ
ssh -i /path/to/your/oracle_ssh_key.key ubuntu@<YOUR_VPS_PUBLIC_IP>
```

> **ข้อแนะนำสำหรับ Oracle Cloud:**
> - User เริ่มต้นของ Ubuntu บน Oracle Cloud คือ `ubuntu`
> - หากติด Permission ของไฟล์ Key บน Linux/Mac ให้รัน `chmod 400 /path/to/key.key` ก่อน

---

## ⚙️ ขั้นตอนที่ 3: Clone โปรเจกต์และรันสคริปต์ติดตั้งอัตโนมัติ

เมื่อเข้ามาที่เซิร์ฟเวอร์แล้ว ให้รันคำสั่งดังนี้:
```bash
# 1. Clone repository จาก branch develop
git clone -b develop https://github.com/changpradub/AlgoTrading.git
cd AlgoTrading

# 2. รันสคริปต์เซ็ตอัป Environment อัตโนมัติ (ติดตั้ง Python 3, PostgreSQL, PM2, venv, logrotate, cron)
sudo bash scripts/setup_vps.sh
```

*สคริปต์จะใช้เวลาประมาณ 2-3 นาทีในการติดตั้งเครื่องมือและสร้างฐานข้อมูล `algo_trading` ให้โดยอัตโนมัติ*

---

## 🔑 ขั้นตอนที่ 4: ตั้งค่าไฟล์ Environment (`.env`) บน VPS

สร้างไฟล์คอนฟิกจากไฟล์ตัวอย่าง:
```bash
cp .env.example .env
nano .env
```

แก้ไขข้อมูลใน `.env` ให้ครบถ้วน:
```ini
# 1. Alpaca Trading API Configuration (Paper Trading)
ALPACA_API_KEY=PKXXXXXXXXXXXXXXXXXX
ALPACA_SECRET_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_FEED=iex
TRADING_MODE=paper

# 2. Database Configuration (สคริปต์ setup_vps.sh สร้างไว้ตามนี้)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=algo_trading
DB_USER=algo_trader
DB_PASSWORD=AlgoTradingSecure2026!

# 3. Notification Configuration (Telegram Bot ภาษาไทย)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=-1001234567890
TELEGRAM_ENABLED=True

# 4. AI Gatekeeper (OpenRouter API)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_MODEL=google/gemini-3.8-flash

# 5. Risk Management & Portfolio
INITIAL_CAPITAL_USD=700.0
MAX_DAILY_LOSS_USD=14.0
MAX_POSITION_SIZE_USD=140.0
TRADE_BUDGET_PER_TRANCHE_USD=20.0
MAX_CONCURRENT_POSITIONS=3
TARGET_SYMBOLS=NVDA,TSM
```
*(กด `Ctrl + O` แล้ว `Enter` เพื่อบันทึก, จากนั้นกด `Ctrl + X` เพื่อออกจาก nano)*

---

## 🗄️ ขั้นตอนที่ 5: เริ่มต้นสร้างตารางในฐานข้อมูล (Database Migration)

รันคำสั่งสร้างตารางทั้ง 10 ตารางใน PostgreSQL:
```bash
.venv/bin/python scripts/init_db.py
```
*ระบบจะแจ้งว่าสร้างตารางครบถ้วน (เช่น `pdt_trades`, `orders`, `positions`, `trades_log`, `ai_analysis`)*

---

## 🧪 ขั้นตอนที่ 6: ตรวจสอบการเชื่อมต่อและทดสอบยิง Telegram

ทดสอบว่าบอทสามารถต่อ Alpaca, Database และยิงแจ้งเตือนภาษาไทยเข้า Telegram ได้จริง:
```bash
# 1. ทดสอบ Health Check & ยิง Heartbeat เข้า Telegram
.venv/bin/python bot.py --health-only

# 2. ทดสอบระบบสรุปผลการเทรดประจำวัน (Daily P/L Summary)
.venv/bin/python bot.py --daily-summary

# 3. ทดสอบรัน Single-cycle ในโหมดจำลอง (Dry-run)
.venv/bin/python bot.py --single-cycle --dry-run
```
*ตรวจเช็คในกลุ่ม Telegram ของคุณว่าได้รับข้อความภาษาไทยครบถ้วน*

---

## 🚀 ขั้นตอนที่ 7: สั่งรันบอททำงานอัตโนมัติด้วย PM2

เมื่อทดสอบผ่านเรียบร้อย ให้เริ่มรันบอทในโหมด Background ตลอด 24 ชั่วโมง:
```bash
# สั่งเริ่มรันผ่าน PM2
pm2 start ecosystem.config.js

# บันทึกสถานะเพื่อให้บอทเปิดขึ้นมาอัตโนมัติทุกครั้งที่เครื่อง Server Reboot
pm2 save
```

---

## 🛠️ คำสั่งที่ใช้ในการมอนิเตอร์และดูแลระบบ (Operations Cheat Sheet)

| คำสั่ง | คำอธิบาย |
|---|---|
| `pm2 status` | ตรวจสอบสถานะการทำงานของบอท, CPU, Memory, และ Uptime |
| `pm2 logs algotrading-bot` | ดู Log การทำงานแบบ Real-time |
| `pm2 restart algotrading-bot` | สั่งรีสตาร์ตบอทใหม่ |
| `pm2 stop algotrading-bot` | สั่งหยุดการทำงานของบอทชั่วคราว |
| `./scripts/deploy.sh` | สคริปต์ดึงโค้ดล่าสุดจาก Git, อัปเดต dependencies, รัน migration, และ reload บอทอัตโนมัติ |
| `cat logs/bot.log \| tail -n 50` | ดูบันทึกการทำงานของบอท 50 บรรทัดล่าสุด |
| `ls -lh /var/backups/algotrading` | ตรวจสอบไฟล์ Backup ฐานข้อมูลที่ถูกสร้างอัตโนมัติทุกวัน |
