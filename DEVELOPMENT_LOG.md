# Personal Algo-Trading Bot — Development Log & Progress Tracker

> **ไฟล์นี้เป็น Single Source of Truth สำหรับบันทึกความคืบหน้าการพัฒนาทั้งหมด**  
> ทุกครั้งที่มีการแก้ไข, เพิ่มฟีเจอร์, ทดสอบ หรือพัฒนาระบบ **ต้องอัปเดตไฟล์นี้อย่างละเอียดเสมอ**

---

## 📌 กฎเหล็กการพัฒนา (Mandatory Development Rules)

1. **อัปเดตไฟล์นี้ทุกครั้ง (Always Update This Log):**
   - ทุกครั้งที่เริ่มหรือจบการทำงานในแต่ละรอบ ต้องบันทึกว่าทำอะไรไปบ้าง (สิ่งที่ทำสำเร็จ, ปัญหาที่พบ, การแก้ไข, และสิ่งที่ต้องทำต่อ)
   - บันทึกอย่างละเอียด ไม่สรุปสั้นเกินไป ระบุชื่อไฟล์และฟังก์ชันที่เกี่ยวข้องเสมอ
2. **หากสับสน ไม่แน่ใจ หรือลืมบริบท ให้กลับมาอ่านก่อนเสมอ (Reset & Realignment Protocol):**
   - ให้อ่าน [UNIFIED_PLAN.md](file:///d:/AlgoTrading/UNIFIED_PLAN.md) เพื่อทำความเข้าใจภาพรวม สถาปัตยกรรม และ 12 กฎเหล็กของระบบ
   - อ่าน [DEVELOPMENT_LOG.md](file:///d:/AlgoTrading/DEVELOPMENT_LOG.md) (ไฟล์นี้) เพื่อเช็คสถานะล่าสุดว่าทำถึงไหน และอะไรคืองานถัดไป
   - ห้ามเดาหรือคิดไปเองเด็ดขาด ให้ยึดตามข้อกำหนดใน [UNIFIED_PLAN.md](file:///d:/AlgoTrading/UNIFIED_PLAN.md)
3. **การทดสอบก่อนบันทึกเสร็จ (Verification):**
   - ทุกโมดูลที่พัฒนาต้องผ่านการทดสอบ (Unit Test หรือ Integration Test) ก่อนติ๊กถูกใน Checklist
4. **ความปลอดภัยและความเสี่ยง (Security & Risk):**
   - API Key Scope = **Trade Only** (ห้ามมีสิทธิ์ Withdraw)
   - ห้าม Commit ไฟล์ `.env`
   - ทุก Order ต้องเป็น **Bracket Order (TP + SL)**
   - คำนึงถึง **PDT Rule (<$25k ห้ามเกิน 3 Day Trades / 5 วัน)** และ **Gap Risk** เสมอ

---

## 🧭 ลิงก์อ้างอิงเอกสารสำคัญ
* **Master Plan:** [UNIFIED_PLAN.md](file:///d:/AlgoTrading/UNIFIED_PLAN.md) (แผนหลัก สถาปัตยกรรม และข้อจำกัดระบบ)
* **แผนเดิมของ ChatGPT (18 Phases):** [chatgpt_personal_algo_trading_bot_plan.md](file:///d:/AlgoTrading/chatgpt_personal_algo_trading_bot_plan.md)
* **แผนเดิมของ Gemini (5 Phases MVP):** [gemini-code-1789988843350.md](file:///d:/AlgoTrading/gemini-code-1789988843350.md)

---

## 📊 ภาพรวมสถานะการพัฒนา (High-Level Progress Tracker)

- [ ] **Phase 1: Foundation & Infrastructure** (กำลังดำเนินการ / รอดำเนินการ)
- [ ] **Phase 2: Core Trading Logic (MVP) & Backtesting**
- [ ] **Phase 3: AI Sentiment Integration (Gatekeeper)**
- [ ] **Phase 4: Fail-safe, Recovery & Risk Hardening**
- [ ] **Phase 5: Paper Trading & VPS Deployment**
- [ ] **Phase 6: Live Trading ($700) & Continuous Improvement**

---

## 📋 Checklist รายละเอียดแต่ละ Phase

### Phase 1: Foundation & Infrastructure
- [ ] จัดโครงสร้างโปรเจกต์ตาม Section 12 ใน `UNIFIED_PLAN.md`
- [ ] สร้างไฟล์ `.env.example` และ `.gitignore`
- [ ] สร้าง `requirements.txt` สำหรับ Python environment
- [ ] ออกแบบและสร้าง Database Schema (PostgreSQL ผ่าน asyncpg + ตาราง `pdt_trades`)
- [ ] ตั้งค่า Structured Logging (JSON format, แยก bot/trades/errors)
- [ ] พัฒนา Alpaca Async Integration Client (`alpaca-py`)
  - [ ] Account & Buying Power
  - [ ] Market Data (WebSocket + REST)
  - [ ] Orders & Positions query
  - [ ] Market Hours (`get_clock()`, `get_calendar()`)
- [ ] พัฒนา Rate Limiter Module (200 req/min บน REST)
- [ ] พัฒนา Market Hours Scheduler (รองรับ Regular Hours, Timezone UTC vs ET vs ICT)
- [ ] พัฒนาระบบแจ้งเตือน Notification (LINE Notify / Telegram Bot)
- [ ] ทดสอบการเชื่อมต่อ Alpaca Paper Trading และ Database ครบวงจร

### Phase 2: Core Trading Logic (MVP) & Backtesting
- [ ] พัฒนา Technical Analysis Module (EMA, RSI, ATR, Support/Resistance)
- [ ] พัฒนา Indicator Warmup Logic (ดึงอย่างน้อย 100 bars ก่อนออก Signal)
- [ ] พัฒนา Strategy Engine (Timeframe: 1H/4H เป็นหลัก, 1D ยืนยัน)
- [ ] พัฒนา Risk Engine:
  - [ ] Hard-coded Max Daily Loss
  - [ ] Max Positions & Duplicate Check
  - [ ] **PDT Counter** (จำกัด Day Trade ไม่เกิน 3 ครั้งใน 5 วัน)
  - [ ] **Gap Risk Assessment** (คำนวณจาก ATR)
- [ ] พัฒนา Position Sizing (ตาม Risk + ATR Gap Factor + Fractional Shares)
- [ ] พัฒนา Order Execution Engine:
  - [ ] **บังคับ Bracket Order (TP + SL) ทุกไม้**
  - [ ] Async Order Status Monitoring & Partial Fill handling
- [ ] พัฒนา State Management & Reconciliation (ซิงค์สถานะ DB กับ Alpaca)
- [ ] พัฒนา Backtesting Framework (จำลอง Slippage, Gap Risk, และสรุป Performance Metrics)

### Phase 3: AI Sentiment Integration
- [ ] พัฒนา News Fetcher Module (ดึงข่าวหุ้นผ่าน News API แบบ async)
- [ ] พัฒนา AI Sentiment Module (OpenRouter API วิเคราะห์และส่งออก JSON)
- [ ] พัฒนา Pre-Market Gap Scan (สแกนข่าวก่อนตลาดเปิด)
- [ ] รวม AI เข้าใน Pipeline เป็น Gatekeeper (Filter สกัด Signal ไม่ใช่คนออกคำสั่ง)
- [ ] บันทึกผลการวิเคราะห์ AI ลงตาราง `ai_analysis`
- [ ] ทำ Backtest เปรียบเทียบผลลัพธ์: มี AI vs ไม่มี AI

### Phase 4: Fail-safe, Recovery & Risk Hardening
- [ ] จัดการ Error & Exception (Network Disconnect, 429 Backoff, DB Timeout)
- [ ] พัฒนา Safe Mode & Automatic Kill Switch
- [ ] ทดสอบ Startup Recovery Flow (Reconcile state, ตรวจ PDT และ Gap Risk ก่อนเริ่ม)
- [ ] Hardening Security (จำกัดสิทธิ์ API Key, Validation ทุก Input)

### Phase 5: Paper Trading & VPS Deployment
- [ ] Setup Ubuntu VPS + PM2 + Python 3 + PostgreSQL
- [ ] ติดตั้ง Log Rotation (`logrotate`) และ Cronjob สำรองฐานข้อมูล (`pg_dump`)
- [ ] ตั้งค่า Git Deployment Workflow (develop → VPS Paper Trading, main → Live)
- [ ] รัน Paper Trading ต่อเนื่อง 2-4 สัปดาห์ พร้อมมอนิเตอร์ผ่าน Notification
- [ ] บันทึกและวิเคราะห์สถิติจริงเทียบกับผล Backtest

### Phase 6: Live Trading & Continuous Improvement
- [ ] สลับเข้าสู่ Live Trading ด้วยเงินทุนจริง ~$700
- [ ] เริ่มต้นเทรดด้วยไม้ขนาดเล็ก (~$20) เพื่อทดสอบ Execution และ Slippage
- [ ] ติดตาม Gap Risk และผลกระทบต่อ Stop Loss ในตลาดจริง
- [ ] ปรับแต่ง Parameters ของกลยุทธ์และตัวกรอง AI จากข้อมูลจริง
- [ ] พัฒนา Web Monitoring Dashboard (Angular / Next.js)

---

## 📝 บันทึกความคืบหน้ารายวัน (Daily Development Log)

> *รูปแบบการบันทึก: ให้เพิ่มรายการใหม่ไว้ด้านบนสุดของส่วนนี้เสมอ*

### [2026-09-22] ศึกษาแผนงานและจัดทำระบบบันทึกการพัฒนา
* **ผู้ปฏิบัติงาน:** Pair Programming (User + Antigravity AI)
* **สิ่งที่ทำไปแล้ว:**
  1. ศึกษาและวิเคราะห์เอกสาร [UNIFIED_PLAN.md](file:///d:/AlgoTrading/UNIFIED_PLAN.md) ครบถ้วนทั้ง 14 ส่วน
  2. สรุปสาระสำคัญ: การเทรด Swing หุ้นสหรัฐฯ (NVDA, TSM) ด้วยงบ $700, กฎ SEC PDT, Timezone handling, Indicator Warmup, Bracket Orders, AI Gatekeeper, และ Risk Management
  3. สร้างไฟล์ [DEVELOPMENT_LOG.md](file:///d:/AlgoTrading/DEVELOPMENT_LOG.md) เพื่อเป็นบันทึกกลางและกำหนดแนวทางการทำงาน
  4. สร้างไฟล์ข้อกำหนด [AGENTS.md](file:///d:/AlgoTrading/AGENTS.md) เพื่อให้ AI Agent ทุกตัวปฏิบัติตามกฎอย่างเคร่งครัด
* **สถานะปัจจุบัน:** พร้อมเริ่ม Phase 1 (Foundation & Infrastructure)
* **ปัญหา/สิ่งที่พบ:**
  - ต้องระวังเรื่อง Timezone ระหว่างเครื่อง Local / VPS (UTC) กับเวลาตลาดหุ้นสหรัฐฯ (ET) และเวลาไทย (ICT)
  - ห้ามลืมกลไก PDT Counter และ Indicator Warmup ตั้งแต่ขั้นตอนแรก
* **สิ่งที่ต้องทำในรอบถัดไป:**
  1. สร้างโครงสร้าง Folder ตามข้อกำหนดใน [UNIFIED_PLAN.md](file:///d:/AlgoTrading/UNIFIED_PLAN.md) Section 12
  2. สร้าง `.env.example`, `.gitignore`, และ `requirements.txt`
  3. ออกแบบ Database Schema DDL scripts
