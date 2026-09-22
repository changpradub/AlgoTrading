# Personal Algo-Trading Bot — Unified Implementation Plan

> **สรุปรวมจาก 2 แผน:**
> - `chatgpt_personal_algo_trading_bot_plan.md` — แผนสถาปัตยกรรมเต็มรูปแบบ 18 Phases
> - `gemini-code-1789988843350.md` — แผน MVP 5 Phases เน้นปฏิบัติจริง
>
> **อัปเดตล่าสุด:** เสริม 12 จุดจาก Gap Analysis (Market Hours, PDT Rule, asyncio, Rate Limiting, Notifications, Warmup, Cost, Timeframe, Gap Risk, Logging, Backup, CI/CD)

---

## 1. Project Overview

| หัวข้อ | รายละเอียด |
|---|---|
| **เป้าหมาย** | สร้างระบบเทรดหุ้นสหรัฐฯ อัตโนมัติ (Automated Trading Bot) สำหรับใช้งานส่วนตัว |
| **เงินทุนเริ่มต้น** | ~$700 |
| **หุ้นเป้าหมาย (เริ่มต้น)** | หุ้นสหรัฐฯ ที่มีความผันผวนสูง เช่น NVDA, TSM (เริ่มจากจำนวนน้อยตัวก่อน) |
| **Trading Style** | **Swing Trading** (ถือ 1-5 วัน) — หลีกเลี่ยง PDT Rule |
| **โหมดการทำงาน** | Backtest → Paper Trading → Live Trading |
| **หลักการหลัก** | Technical Analysis สร้าง Signal → AI กรองข่าว → Risk Engine ควบคุมความเสี่ยง → Order Engine ส่งคำสั่ง |

### หลักคิดสำคัญ

> **เป้าหมายระยะแรกไม่ใช่การทำกำไรสูงสุด แต่คือการสร้างระบบที่ทำงานถูกต้อง ควบคุมความเสี่ยงได้ และสามารถตรวจสอบย้อนหลังได้**

---

## 2. Technology Stack

| Layer | เทคโนโลยี | หมายเหตุ |
|---|---|---|
| **Broker & API** | Alpaca Trading API | Paper Trading → Live Trading, Zero Commission, Fractional Shares |
| **Backend / Logic** | Python 3.x | พร้อม libs: `alpaca-py`, `asyncpg`, `pandas`, `ta-lib` |
| **Concurrency** | **asyncio** (Python native) | WebSocket, Order monitoring, AI calls ทำงานแบบ async |
| **Database** | PostgreSQL | เก็บ Orders, Positions, Logs, Bot State, AI Analysis |
| **DB Driver** | **asyncpg** | Async PostgreSQL driver (รองรับ asyncio) |
| **AI / Sentiment** | OpenRouter API | พิจารณา Ollama / Local LLM ในอนาคต |
| **Server** | Ubuntu 24.04 VPS | |
| **Process Manager** | PM2 | Auto-restart, Background Process (เหมาะกับ single-process bot) |
| **Notification** | **LINE Notify / Telegram Bot** | แจ้งเตือน Trade, Risk Event, Bot Status เรียลไทม์ |
| **Dashboard (อนาคต)** | Angular หรือ Next.js + Nginx | ไม่ใช่ Priority แรก, พัฒนาหลัง Trading Core เสร็จ |
| **Development** | Git, VS Code / Antigravity IDE, `.env` | |

---

## 3. System Architecture — Core Pipeline

```text
┌─────────────────────────────────────────────────────────────────────┐
│                     PERSONAL ALGO-TRADING BOT                       │
│                       (asyncio event loop)                          │
│                                                                     │
│  ┌────────────────┐                                                 │
│  │ Market Hours    │ ← Alpaca get_clock() / get_calendar()          │
│  │ Scheduler       │ ← เทรดเฉพาะ Regular Hours (09:30-16:00 ET)    │
│  │ (Timezone: UTC) │ ← Idle นอก Market Hours                       │
│  └───────┬────────┘                                                 │
│          │ Market Open                                              │
│          v                                                          │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐      │
│  │  Market Data  │──>│ Technical Engine  │──>│   Strategy   │      │
│  │  (WS + REST)  │    │ (EMA, RSI, ATR)  │    │   Engine     │      │
│  │  Rate Limited  │    │ (Warmup: 100bars)│    │ (1H/4H + 1D)│      │
│  └──────────────┘    └──────────────────┘    └──────┬───────┘      │
│                                                      │              │
│                                              Trading Signal         │
│                                                      │              │
│                                                      v              │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐      │
│  │  News Feed    │──>│   AI Sentiment   │──>│  Gatekeeper  │      │
│  │  (News API)   │    │  (OpenRouter)    │    │  (Pass/Block)│      │
│  │  +Pre-Market  │    │  +Gap Risk Scan  │    │              │      │
│  └──────────────┘    └──────────────────┘    └──────┬───────┘      │
│                                                      │              │
│                                              Approved Signal        │
│                                                      │              │
│                                                      v              │
│                      ┌──────────────────┐    ┌──────────────┐      │
│                      │   Risk Engine    │<──│  Position    │      │
│                      │ (Limits, Kill SW)│    │  Sizing      │      │
│                      │ (PDT Counter)    │    │ (Gap Risk)   │      │
│                      └────────┬─────────┘    └──────────────┘      │
│                               │                                     │
│                        Approved + Sized                              │
│                               │                                     │
│                               v                                     │
│                      ┌──────────────────┐    ┌──────────────┐      │
│                      │ Order Execution  │──>│ Notification │      │
│                      │ (Bracket Order)  │    │ (LINE/TG)    │      │
│                      │ TP / SL / Scale  │    │              │      │
│                      └────────┬─────────┘    └──────────────┘      │
│                               │                                     │
│                               v                                     │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐      │
│  │  PostgreSQL   │<──│ State Management │──>│  Monitoring  │      │
│  │  (All Logs)   │    │ (Reconcile)      │    │  & Alerts    │      │
│  │  (async)      │    │ (Stateless)      │    │              │      │
│  └──────────────┘    └──────────────────┘    └──────────────┘      │
│                                                                     │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  v
                          ┌──────────────┐
                          │  Alpaca API   │
                          │  (Paper/Live) │
                          └──────┬───────┘
                                 │
                                 v
                          US Stock Market
```

---

## 4. Core Components — รายละเอียด

### 4.0 Market Hours Scheduler ⭐ NEW

Bot ทำงานจากไทย (UTC+7) แต่เทรดหุ้นสหรัฐฯ (US Eastern) ต้องจัดการ timezone อย่างเป็นระบบ

**Market Hours (US Eastern Time):**
```text
├── Pre-Market:     04:00 - 09:30 ET
├── Regular Hours:  09:30 - 16:00 ET  ← Bot เทรดช่วงนี้เท่านั้น (V1)
├── After-Hours:    16:00 - 20:00 ET
└── Closed:         20:00 - 04:00 ET + US Holidays

เทียบเวลาไทย (UTC+7):
├── Regular Hours:  20:30 - 03:00 (คืนถัดไป)
└── Daylight Saving: ปรับ ±1 ชม. (มี.ค. - พ.ย.)
```

**กฎ:**
- ตรวจสอบ Market Hours ผ่าน Alpaca `get_clock()` API
- จัดการ US Holidays ผ่าน `get_calendar()` API
- **Timestamp ทั้งหมดใน DB เก็บเป็น UTC**
- Bot idle นอก Market Hours (ไม่ส่ง Order, ลด resource usage)
- V1: เทรดเฉพาะ Regular Hours (09:30-16:00 ET) เท่านั้น
- ก่อนตลาดเปิด: ดึงข่าว + AI Pre-Market Scan

---

### 4.1 Market Data Module
- ดึงข้อมูลราคาผ่าน Alpaca **WebSocket** (Real-time, หลัก) + REST API (fallback)
- รองรับ Historical Data สำหรับ Backtesting
- ตรวจจับ Data Staleness (ข้อมูลเก่า/ค้าง)
- จัดการ Connection drop & auto-reconnect
- **Rate Limiter:** จำกัด REST API ไม่เกิน 200 req/min (Alpaca limit)
- จัดการ HTTP 429 (Too Many Requests) ด้วย **exponential backoff**
- ใช้ WebSocket เป็นหลักเพื่อประหยัด API requests

---

### 4.2 Technical Analysis Engine
- คำนวณ Indicators: **EMA, RSI, ATR, Support/Resistance** (เริ่มจากพื้นฐาน)
- สามารถเพิ่ม Indicators ได้ในอนาคต (MACD, Bollinger, Volume Profile, etc.)
- ใช้ข้อมูลเดียวกันได้ทั้ง Live Trading และ Backtesting
- **Warmup Period:**
  - เมื่อ Bot เริ่มทำงาน → ดึง Historical bars ย้อนหลังอย่างน้อย **100 bars** ก่อน
  - คำนวณ `WARMUP_BARS = max(all indicator periods) + safety buffer`
  - **ห้ามสร้าง Signal จนกว่า Warmup จะเสร็จ**

---

### 4.3 Strategy Engine
- กำหนดกฎ Entry / Exit ที่ชัดเจน สามารถทำซ้ำได้
- สร้าง Trading Signal: **BUY / SELL / HOLD**
- Strategy Configuration เก็บใน Database (ปรับได้โดยไม่ต้องแก้โค้ด)
- เริ่มจาก Strategy ที่เรียบง่ายก่อน
- **Timeframe:**
  - Primary: **1-Hour (1H)** หรือ **4-Hour (4H)**
  - Confirmation: **Daily (1D)**
  - Trading Style: **Swing Trading** (ถือ 1-5 วัน) — หลีกเลี่ยง PDT Rule

---

### 4.4 AI Sentiment Module (Gatekeeper)
- ดึงข่าวล่าสุดของหุ้นเป้าหมายผ่าน News API
- ส่งข่าวให้ LLM วิเคราะห์ ได้ Structured Output:
  - `sentiment` (positive / neutral / negative)
  - `confidence` (0-1)
  - `risk_event` (boolean)
  - `impact` (low / medium / high)
- **AI ทำหน้าที่เป็น Filter/Gatekeeper เท่านั้น — ไม่ตัดสินใจซื้อขายเอง**
- สามารถ Pass, Block, หรือเพิ่ม Warning ให้ Signal
- **Pre-Market Scan:** ตรวจข่าวก่อนตลาดเปิดเพื่อประเมิน **Gap Risk** ของหุ้นที่ถืออยู่

---

### 4.5 Risk Engine (ด่านสุดท้ายก่อนส่ง Order)

| กฎ | รายละเอียด |
|---|---|
| Risk per Trade | กำหนด % ความเสี่ยงต่อ Trade (เช่น 1-2% ของ Equity) |
| Position Size | คำนวณจาก Risk, Entry Price, Stop Loss |
| Max Exposure | จำกัดเงินลงทุนรวมทั้งหมด |
| Max Daily Loss | **Hard-coded** ขาดทุนสูงสุดต่อวัน หยุดเทรดอัตโนมัติ |
| Max Positions | จำกัดจำนวน Position พร้อมกัน |
| Duplicate Check | ป้องกันส่ง Order ซ้ำ |
| Stale Data Check | ไม่เทรดถ้าข้อมูลเก่าเกินไป |
| **PDT Protection** ⭐ | **นับ Day Trade ใน 5 วัน, บล็อกถ้าถึง 3 ครั้ง (PDT Rule, equity < $25k)** |
| **Gap Risk** ⭐ | **คำนวณ overnight gap risk ด้วย ATR, ปรับ position size ตาม worst-case** |
| **Kill Switch** | ระงับ Bot ทันทีผ่าน DB Flag หรือ API Endpoint |

> **Risk Engine สามารถปฏิเสธ Trade ได้แม้ Strategy จะสร้าง BUY Signal**

**PDT Rule Detail (สำคัญมากสำหรับพอร์ต $700):**
```text
Pattern Day Trading Rule (SEC):
- บัญชี Equity < $25,000
- ห้าม Day Trade (ซื้อ+ขายวันเดียว) เกิน 3 ครั้ง ใน 5 วันทำการ
- ถ้าทำเกิน → บัญชีถูก Flag → จำกัดการเทรด 90 วัน

V1 Strategy: Swing Trading (ถือข้ามคืน) → หลีกเลี่ยง PDT โดยธรรมชาติ
แต่ Risk Engine ต้องมี PDT Counter ป้องกันไว้เสมอ
```

**Gap Risk Detail:**
```text
Swing Trading = ถือข้ามคืน → เจอ Gap Risk
ตัวอย่าง: ซื้อ NVDA $140, SL $135 → เช้าเปิด $125 → SL ไม่ trigger

ป้องกัน:
- ใช้ ATR คำนวณ expected gap range
- Position Size ต้องรองรับ worst-case gap (เช่น 2x ATR)
- ตรวจราคาเปิดทุกเช้า → ถ้า gap เกินเกณฑ์ → แจ้งเตือน
- AI Pre-Market Scan ช่วยประเมินก่อนตลาดเปิด
```

---

### 4.6 Position Sizing
- คำนวณขนาด Position ตาม Risk-based formula
- พิจารณา: Equity, Max Risk %, Entry Price, Stop Loss, Buying Power
- รองรับ **Fractional Shares** (Alpaca)
- เริ่มต้นด้วยงบต่อไม้ ~$20 (Scaling)
- **Gap Risk Factor:** ปรับ Position Size ลงถ้าหุ้นมี ATR สูง (overnight risk)

---

### 4.7 Order Execution Engine
- ส่ง Order ผ่าน Alpaca API (**async**)
- **ทุก Buy Order ต้องแนบ Bracket Order (Take Profit + Stop Loss) ทันที**
- รองรับ: Market/Limit, Bracket, Scaling (แบ่งไม้), Partial Fill
- ติดตาม Order Status จนกว่าจะ Filled/Rejected (**async monitoring**)
- รองรับ Cancel, Replace, Retry
- **การ Submit สำเร็จ ≠ Position สำเร็จ** — ต้องติดตามผลจริง
- **ส่ง Notification** ทุกครั้งที่ Order Filled / Rejected / Cancelled

---

### 4.8 State Management & Recovery
- บันทึกทุก State ลง PostgreSQL (ไม่พึ่งพา Memory)
- **Stateless Execution**: สคริปต์ต้องอ่าน State จาก DB เสมอ
- เมื่อ Bot Restart: ตรวจสอบสถานะจริงจาก Alpaca → Reconcile กับ DB → แล้วจึงเริ่มทำงานต่อ
- **ห้ามส่ง Order ใหม่เพียงเพราะอ่าน State เดิมไม่ได้**

---

### 4.9 Notification System ⭐ NEW

Bot ทำงานบน VPS ช่วงดึก (เวลาไทย) — ต้องแจ้งเตือนเมื่อเกิดเหตุสำคัญ

**ช่องทาง:** LINE Notify หรือ Telegram Bot (เริ่มจากอย่างใดอย่างหนึ่ง)

| เหตุการณ์ | ระดับ | ตัวอย่าง |
|---|---|---|
| Order Filled | 📗 Info | "NVDA BUY 0.15 shares @ $140.50, TP=$148, SL=$135" |
| Order Rejected / Failed | 📙 Warning | "NVDA BUY rejected: insufficient buying power" |
| Daily P/L Summary | 📗 Info | "Daily P/L: +$3.20 (+0.46%), Equity: $703.20" |
| Risk Event (Max Loss) | 🔴 Critical | "⚠️ Daily Loss Limit reached (-$14). Trading paused." |
| Kill Switch Activated | 🔴 Critical | "🛑 KILL SWITCH activated. All trading stopped." |
| Bot Error / Crash | 🔴 Critical | "❌ Bot crashed: ConnectionError. PM2 restarting..." |
| WebSocket Disconnect | 📙 Warning | "WS disconnected. Reconnecting in 5s..." |
| PDT Warning | 📙 Warning | "⚠️ PDT Count: 2/3 in 5 days. 1 remaining." |
| Gap Alert | 📙 Warning | "NVDA gap -3.2% at open. Current SL may not cover." |
| Bot Started / Stopped | 📗 Info | "Bot started. Market opens in 2h 15m." |

---

## 5. Database Schema (High-Level)

```text
PostgreSQL (asyncpg driver)
├── trades_log          — บันทึกทุก Trade (signal, entry, exit, P/L)
├── orders              — Order history & status
├── positions           — Current & historical positions
├── portfolio_state     — Account equity, cash, buying power snapshots
├── signals             — Trading signals generated
├── ai_analysis         — AI sentiment results
├── news_cache          — ข่าวที่ดึงมาวิเคราะห์
├── risk_events         — Risk violations & actions taken
├── system_events       — Bot lifecycle events (start, stop, error)
├── bot_state           — Current bot state (running, paused, error)
├── strategy_config     — Strategy parameters (configurable)
└── pdt_trades          — Day Trade counter สำหรับ PDT Rule ⭐ NEW
```

### Data Retention & Backup ⭐ NEW

| Data | Retention | Backup |
|---|---|---|
| trades_log | ถาวร | Daily pg_dump |
| orders | ถาวร | Daily pg_dump |
| positions | ถาวร | Daily pg_dump |
| portfolio_state | 1 ปี | Weekly backup |
| ai_analysis | 6 เดือน | Monthly backup |
| news_cache | 3 เดือน | ไม่ backup (ดึงใหม่ได้) |
| system_events | 6 เดือน | Monthly backup |
| bot_state | Current only | Real-time (สำคัญ) |

**Backup Strategy:**
```bash
# Daily automated backup via cron (บน VPS)
0 5 * * * pg_dump algo_trading | gzip > /backup/algo_$(date +\%Y\%m\%d).sql.gz

# เก็บ backup 30 วัน, ลบของเก่าอัตโนมัติ
find /backup/ -name "algo_*.sql.gz" -mtime +30 -delete
```

---

## 6. Development Phases — แผนรวม

> ผสมความครบถ้วนของแผน ChatGPT (18 phases) เข้ากับความกระชับของแผน Gemini (5 phases)
> แบ่งเป็น **6 Phases หลัก** ที่สามารถทำงานได้จริง

---

### Phase 1: Foundation & Infrastructure
**เป้าหมาย:** เตรียมทุกอย่างให้พร้อมพัฒนา

- [ ] สร้าง Alpaca Account + Paper Trading API Key (**Trade Only scope**)
- [ ] ตั้งค่า Python environment + dependencies (`alpaca-py`, `asyncpg`, `pandas`, `ta-lib`, `structlog`)
- [ ] ตั้งค่า PostgreSQL + สร้าง Database Schema (รวม `pdt_trades` table)
- [ ] ตั้งค่า Git repository + project structure + **.gitignore** (ห้าม commit `.env`)
- [ ] ตั้งค่า `.env` สำหรับ Environment Variables
- [ ] ตั้งค่า **Structured Logging** (JSON format, แยกไฟล์ bot/trades/errors)
- [ ] เขียน Alpaca API Integration Module (**async**):
  - อ่าน Account, Buying Power
  - ดึง Market Data (WebSocket + REST)
  - อ่าน Orders, Positions
  - ส่ง/ยกเลิก Order
  - **get_clock() / get_calendar()** สำหรับ Market Hours
- [ ] เขียน **Rate Limiter** module (200 req/min)
- [ ] เขียน **Market Hours Scheduler** (idle นอก market hours)
- [ ] ทดสอบ API Integration กับ Paper Trading
- [ ] ตั้งค่า **LINE Notify หรือ Telegram Bot** สำหรับ Notification

**Deliverable:** สามารถเชื่อมต่อ Alpaca ได้ + ดึงข้อมูลราคาได้ + DB พร้อมใช้ + แจ้งเตือนได้

---

### Phase 2: Core Trading Logic (MVP)
**เป้าหมาย:** สร้าง Trading Pipeline ที่ทำงานได้ครบวงจร (ยังไม่มี AI)

- [ ] เขียน Technical Analysis Module (EMA, RSI, **ATR**, Support/Resistance)
- [ ] เขียน **Indicator Warmup** logic (ดึง 100+ historical bars ก่อนเริ่ม)
- [ ] เขียน Strategy Engine + Signal Generation (BUY/SELL/HOLD)
  - Primary Timeframe: **1H หรือ 4H**
  - Confirmation: **1D**
- [ ] เขียน Risk Engine พื้นฐาน:
  - Max Daily Loss (Hard-coded)
  - Max Positions
  - Duplicate Order prevention
  - **PDT Counter** (นับ Day Trade ใน 5 วัน, block ถ้าถึง 3)
  - **Gap Risk** assessment (ATR-based)
- [ ] เขียน Position Sizing Module (Risk-based + **Gap Risk Factor**)
- [ ] เขียน Order Execution Engine (**async**):
  - Buy/Sell Order
  - **Bracket Order (TP + SL) ผูกทุก Order**
  - Scaling (แบ่งไม้)
  - Order status tracking (async monitoring)
- [ ] เขียน State Management:
  - บันทึก State ลง DB
  - อ่าน State จาก DB เมื่อ Restart
  - Reconcile กับ Alpaca
- [ ] เขียน Notification integration (ส่งแจ้งเตือนเมื่อ Order Filled / Risk Event)
- [ ] **Backtesting Framework:**
  - จำลอง Entry/Exit/TP/SL/Scaling
  - **จำลอง Slippage + Gap Risk**
  - วัดผล: Total Return, Win Rate, Profit Factor, Max Drawdown, Sharpe Ratio
  - ทดสอบกับหลายสภาวะตลาด (ขาขึ้น, ขาลง, Sideways)

**Deliverable:** Bot ที่เทรดได้จาก Technical Signal + Backtest results + แจ้งเตือน

---

### Phase 3: AI Sentiment Integration
**เป้าหมาย:** เพิ่ม AI เป็น Gatekeeper ให้กับ Trading Signal

- [ ] เขียน News Fetcher Module (News API) — **async**
- [ ] เขียน AI Sentiment Analysis Module (OpenRouter API) — **async**:
  - Input: ข่าวล่าสุดของหุ้น
  - Output: Structured JSON (sentiment, confidence, risk_event, impact)
- [ ] เขียน **Pre-Market Scan** (ตรวจข่าวก่อนตลาดเปิดเพื่อประเมิน Gap Risk)
- [ ] รวม AI เข้ากับ Pipeline:
  - Technical Signal → AI Sentiment Check → Risk Engine → Order
- [ ] เก็บ AI Analysis ลง Database
- [ ] เปรียบเทียบ Performance: Strategy เดี่ยว vs Strategy + AI
- [ ] Backtest ซ้ำกับ AI Filter

**Deliverable:** Trading Pipeline ครบถ้วน พร้อม AI Gatekeeper + Pre-Market Scan

---

### Phase 4: Fail-safe, Recovery & Risk Hardening
**เป้าหมาย:** ทำให้ระบบทนต่อความผิดพลาดในโลกจริง

- [ ] จัดการ Error Cases ทั้งหมด:
  - API Failure / Timeout / **Rate Limit (429)**
  - Network / WebSocket Disconnect → Auto-reconnect
  - Database Error
  - Partial Fill handling
  - Order Rejection handling
  - Position Mismatch detection
- [ ] Implement Safe Mode:
  - เมื่อเกิดเหตุร้ายแรง → หยุดเปิด Trade ใหม่
  - Cancel Pending Orders ตามเงื่อนไข
  - **ส่ง Notification ทันที**
- [ ] Implement Kill Switch:
  - DB Flag หรือ API Endpoint เพื่อหยุด Bot ทันที
  - **ส่ง Critical Notification**
- [ ] **Security Hardening:**
  - API Key Scope: **Trade Only** (ห้าม Withdraw)
  - Hard-coded Risk Limits ใน Risk Engine
  - Stateless Execution (พึ่ง DB เป็นหลัก)
- [ ] Startup Recovery Flow:
  - ตรวจสอบสถานะจริง Alpaca → Reconcile DB → Resume
  - **ตรวจสอบ PDT count** ก่อนเริ่มเทรด
  - **ตรวจ Gap Risk** ของ Position ที่ถืออยู่

**Deliverable:** ระบบที่ทนต่อความผิดพลาดและปลอดภัย

---

### Phase 5: Paper Trading & VPS Deployment
**เป้าหมาย:** ทดสอบระบบในสภาวะตลาดจริงบน Server

- [ ] Deploy ขึ้น Ubuntu VPS:
  - ติดตั้ง Python, PostgreSQL, Application
  - ตั้งค่า PM2 สำหรับ Process Management (`pm2 start bot.py --interpreter python3`)
  - ตั้งค่า Firewall / Security
  - ตั้งค่า **Structured Logging + Log Rotation** (logrotate, เก็บ 30 วัน)
  - ตั้งค่า **DB Backup cron job** (daily pg_dump)
- [ ] ตั้งค่า **Git deploy workflow:**
  ```
  develop branch → Paper Trading (VPS)
  main branch    → Production (Live)
  ```
- [ ] รัน Paper Trading **อย่างน้อย 2-4 สัปดาห์**
- [ ] ทดสอบ End-to-End ทุก Component:
  - Market Hours → Warmup → Market Data → Technical → Strategy → AI → Risk → PDT Check → Order → Fill → State → Notification → Recovery
- [ ] ทดสอบกรณีผิดพลาด:
  - Bot Restart, Server Restart, API Error, Network Drop, **Rate Limit**
- [ ] ตรวจสอบ **Timezone handling** (UTC storage, ET trading, ICT display)
- [ ] เก็บ Performance Data และเปรียบเทียบกับ Backtest
- [ ] (Optional) Monitoring Dashboard เบื้องต้น

**Deliverable:** Bot ทำงานได้จริงบน VPS ด้วย Paper Trading + Notification + Backup

---

### Phase 6: Live Trading & Continuous Improvement
**เป้าหมาย:** เริ่ม Live Trading อย่างระมัดระวัง + ปรับปรุงต่อเนื่อง

- [ ] สลับจาก Paper → Live Trading ($700)
- [ ] **เริ่มจาก Risk ต่ำที่สุด:**
  - Position size เล็ก
  - จำนวนหุ้นน้อยตัว
  - Kill Switch พร้อมใช้งาน
  - **PDT Counter active**
- [ ] ตรวจสอบ Live Execution:
  - Slippage
  - Fill quality
  - **Gap behavior** (ราคาเปิดจริง vs SL)
  - ความแตกต่างระหว่าง Backtest / Paper / Live
- [ ] Performance Analysis ต่อเนื่อง:
  - Win/Loss, Profit Factor, Drawdown, Expectancy
  - AI Effectiveness
  - Strategy Behavior ในแต่ละ Market Regime
  - **ค่าใช้จ่ายจริง vs ผลตอบแทน**
- [ ] Optimization (ต้อง Backtest ซ้ำก่อนใช้จริง):
  - ปรับ Strategy Parameters
  - ปรับ Risk Limits
  - ปรับ AI Filter
- [ ] Monitoring Dashboard (Angular / Next.js):
  - Bot Status, Account, P/L, Positions, Orders, Risk, Alerts

**Deliverable:** Live Trading ที่ทำงานได้จริง + Dashboard

---

## 7. Strict Constraints & Security

**กฎเหล็กที่ต้องปฏิบัติตามเสมอ:**

1. **API Key Scope = Trade Only** — ห้ามมีสิทธิ์ Withdraw เด็ดขาด
2. **Hard-coded Limits** — งบต่อไม้ และ Max Daily Loss ต้อง Hard-code ใน Risk Engine
3. **Stateless Execution** — ห้ามเก็บ State ไว้ใน Memory เป็นหลัก ให้พึ่ง Database
4. **Kill Switch** — ต้องมีกลไกหยุด Bot ได้ทันที + ส่ง Notification
5. **No Order Without Reconcile** — ห้ามส่ง Order ใหม่ถ้ายังไม่ได้ Reconcile State
6. **Every Order = Bracket Order** — ทุก Buy ต้องมี TP + SL เสมอ
7. **AI ≠ Decision Maker** — AI เป็นแค่ Filter ไม่ใช่ผู้ตัดสินใจซื้อขาย
8. **Backtest → Paper → Live** — ห้ามข้ามขั้นตอน
9. **PDT Rule** ⭐ — ห้าม Day Trade เกิน 3 ครั้ง / 5 วัน (equity < $25k)
10. **No Signal Before Warmup** ⭐ — ห้ามสร้าง Signal ก่อน Indicator Warmup เสร็จ
11. **Market Hours Only** ⭐ — ห้ามส่ง Order นอก Regular Market Hours (V1)
12. **All Timestamps = UTC** ⭐ — เก็บเวลาเป็น UTC เสมอ, แปลงเมื่อแสดงผล

---

## 8. Operating Cost Estimate ⭐ NEW

| รายการ | ประมาณการ/เดือน | หมายเหตุ |
|---|---|---|
| VPS (Ubuntu, 2GB RAM) | $5-10 | DigitalOcean / Linode / Vultr |
| Alpaca API | $0 | Paper + Live ฟรี, Zero Commission |
| Alpaca Market Data | $0 (Free plan) | IEX data (ไม่ใช่ full SIP) |
| OpenRouter API (AI) | $1-5 | ขึ้นกับ model + จำนวน calls/วัน |
| News API | $0-29 | Free plan มี limit |
| LINE Notify / Telegram | $0 | ฟรี |
| Domain + SSL (Dashboard) | $0-15 | ถ้าทำ Dashboard ในอนาคต |
| **รวมประมาณ** | **$6-60/เดือน** | |

> **สำคัญ:** ค่าใช้จ่าย $6-60/เดือน vs เงินทุน $700
> ต้องมั่นใจว่า Strategy สร้างผลตอบแทนคุ้มค่าใช้จ่ายในระยะยาว

**Tips ลดค่าใช้จ่าย:**
- ใช้ Alpaca Free Data Plan ก่อน (IEX data เพียงพอสำหรับ Swing Trading)
- ใช้ OpenRouter model ที่ถูก (GPT-4o-mini, Gemini Flash) สำหรับ Sentiment
- ใช้ News API Free plan (จำกัด 100 req/วัน → เพียงพอสำหรับ 2-3 หุ้น)

---

## 9. สิ่งที่อยู่นอกขอบเขต Version 1

ไม่ทำในช่วงแรก เพื่อควบคุมความซับซ้อน:

- Deep Learning / Reinforcement Learning
- LLM ตัดสินใจซื้อขายโดยตรง
- หุ้นจำนวนมาก (เริ่ม 2-3 ตัว)
- Options / Futures / Leverage
- High-Frequency Trading
- Distributed Infrastructure
- Pre-Market / After-Hours Trading
- Multi-strategy switching อัตโนมัติ

---

## 10. สรุปเปรียบเทียบ 2 แผนต้นฉบับ

| หัวข้อ | ChatGPT Plan | Gemini Plan | แผนรวม (Unified) |
|---|---|---|---|
| **จำนวน Phases** | 18 | 5 | **6** (จัดกลุ่มใหม่) |
| **รายละเอียด** | ละเอียดมาก, ครอบคลุมทุกด้าน | กระชับ, เน้น MVP | รวมจุดแข็งทั้งคู่ |
| **Process Manager** | Docker / systemd | PM2 | **PM2** (เหมาะกับ single bot) |
| **หุ้นเป้าหมาย** | ไม่ระบุ | NVDA, TSM | **NVDA, TSM** (เริ่มต้น) |
| **งบต่อไม้** | ไม่ระบุ | ~$20 | **~$20** (Scaling) |
| **Bracket Order** | กล่าวถึง | บังคับทุก Order | **บังคับทุก Order** |
| **Stateless** | กล่าวถึง Recovery | เน้น Stateless Execution | **Stateless เป็นหลัก** |
| **API Security** | ไม่ระบุ | Trade Only, No Withdraw | **Trade Only** |
| **Kill Switch** | กล่าวถึง | บังคับ | **บังคับ** |
| **Dashboard** | Angular / Next.js | Optional/Future | **Phase 6** (ไม่เร่ง) |
| **Backtesting** | Phase แยก (ละเอียด) | ไม่ระบุ | **อยู่ใน Phase 2** |

---

## 11. CI/CD & Deployment Workflow ⭐ NEW

```text
Git Branching (เรียบง่าย สำหรับ single developer):
├── main        → Production (Live Trading on VPS)
├── develop     → Staging (Paper Trading on VPS)
└── feature/*   → Local development & testing

Deploy Process:
1. พัฒนา feature → push to feature/* branch
2. Merge to develop → deploy to VPS (Paper Trading)
3. Paper Trading ผ่าน → Merge to main
4. SSH to VPS → git pull → pm2 restart bot
5. ตรวจสอบ logs + Notification → ยืนยัน bot ทำงานปกติ

อนาคต: GitHub Actions สำหรับ automated testing + deploy
```

---

## 12. Recommended Project Structure

```text
D:\AlgoTrading\
├── README.md
├── UNIFIED_PLAN.md              <-- แผนนี้
├── DEVELOPMENT_LOG.md           <-- บันทึกความคืบหน้าและกฎการพัฒนา (อัปเดตทุกครั้ง)
├── AGENTS.md                    <-- กฎข้อบังคับของ Agent
├── .env                          <-- API Keys, DB Config (ห้าม commit!)
├── .gitignore
├── requirements.txt
├── bot.py                        <-- Main entry point (asyncio.run)
│
├── config/
│   ├── settings.py               <-- Configuration loader
│   └── constants.py              <-- Hard-coded limits (PDT, Risk, etc.)
│
├── core/
│   ├── scheduler.py              <-- Market Hours Scheduler ⭐
│   ├── market_data.py            <-- Market Data Module (async + rate limiter)
│   ├── technical.py              <-- Technical Analysis Engine (+ warmup)
│   ├── strategy.py               <-- Strategy Engine (1H/4H + 1D)
│   ├── ai_sentiment.py           <-- AI Sentiment Module (+ pre-market scan)
│   ├── risk_engine.py            <-- Risk Engine (+ PDT + Gap Risk)
│   ├── position_sizing.py        <-- Position Sizing Calculator (+ ATR factor)
│   ├── order_execution.py        <-- Order Execution Engine (async)
│   └── state_manager.py          <-- State Management & Recovery
│
├── db/
│   ├── connection.py             <-- DB Connection (asyncpg)
│   ├── models.py                 <-- Table Models
│   └── migrations/               <-- Schema Migrations
│
├── notifications/                <-- ⭐ NEW
│   ├── notifier.py               <-- Notification Interface
│   ├── line_notify.py            <-- LINE Notify
│   └── telegram_bot.py           <-- Telegram Bot (backup)
│
├── backtest/
│   ├── engine.py                 <-- Backtesting Engine
│   └── reports.py                <-- Performance Reports
│
├── monitoring/
│   ├── alerts.py                 <-- Alert System
│   └── health_check.py           <-- System Health Monitor
│
├── utils/                        <-- ⭐ NEW
│   ├── rate_limiter.py           <-- API Rate Limiter
│   ├── timezone.py               <-- Timezone utilities (UTC/ET/ICT)
│   └── logger.py                 <-- Structured Logging setup
│
├── tests/
│   ├── test_strategy.py
│   ├── test_risk.py
│   ├── test_order.py
│   ├── test_pdt.py               <-- ⭐ PDT Rule tests
│   └── test_scheduler.py         <-- ⭐ Market Hours tests
│
├── scripts/                      <-- ⭐ NEW
│   ├── backup_db.sh              <-- Database backup script
│   └── deploy.sh                 <-- VPS deploy script
│
└── logs/
    ├── bot.log                   <-- General log (JSON)
    ├── trades.log                <-- Trade-specific log
    └── errors.log                <-- Error-only log
```

---

## 13. Core Principles (อัปเดต)

1. Technical Strategy เป็นแกนหลักของการสร้าง Signal
2. AI เป็นตัวช่วยวิเคราะห์ข่าวและเป็น Filter
3. ทุก Trade ต้องผ่าน Risk Management
4. Position Size ต้องสัมพันธ์กับ Risk **และ Gap Risk**
5. Order ต้องมีการติดตามหลังส่งคำสั่ง
6. Database ต้องเก็บสถานะสำคัญของระบบ
7. Bot ต้องสามารถ Reconcile สถานะกับ Broker ได้
8. ระบบต้อง Recover หลัง Restart หรือ Connection Failure
9. ต้องมี Fail-safe และ Kill Switch
10. ต้อง Backtest ก่อน Paper Trading
11. ต้อง Paper Trading ก่อน Live Trading
12. Live Trading ต้องเริ่มด้วย Risk ต่ำ
13. ทุก Trade ต้องสามารถตรวจสอบย้อนหลังได้
14. Strategy ต้องสามารถวัด Performance ได้
15. การปรับปรุง Strategy ต้องอาศัยข้อมูลและการทดสอบ ไม่ใช่ผลลัพธ์ระยะสั้น
16. **ต้องจัดการ Timezone อย่างเป็นระบบ (UTC storage)**
17. **ต้องปฏิบัติตาม PDT Rule อย่างเคร่งครัด**
18. **Indicator ต้อง Warmup ก่อนสร้าง Signal**
19. **ต้องมี Notification System แจ้งเตือนเรียลไทม์**
20. **ต้องคำนึงถึง Gap Risk สำหรับ Overnight Positions**

---

## 14. Final Project Goal

เป้าหมายสุดท้ายคือสร้างระบบที่สามารถ:

**ตรวจสอบ Market Hours → Warmup Indicators → รับข้อมูลตลาด → วิเคราะห์ Technical (1H/4H + 1D) → สร้าง Signal → ตรวจสอบข่าวด้วย AI (+ Pre-Market Scan) → ตรวจ PDT Rule → ประเมินความเสี่ยง (+ Gap Risk) → คำนวณ Position → ส่งคำสั่ง (Bracket Order) → แจ้งเตือนผ่าน LINE/Telegram → ติดตาม Position → ปิด Position ตาม Strategy → บันทึกข้อมูล → Monitor → Recover เมื่อเกิดปัญหา → วิเคราะห์ Performance → ปรับปรุง Strategy**

โดยระบบสามารถทำงานอัตโนมัติบน VPS (asyncio) และสามารถเปลี่ยนผ่านจาก **Backtest → Paper Trading → Live Trading** ได้อย่างเป็นระบบ

> **หลักคิดของโครงการ: สร้างระบบ Trading ที่ควบคุมได้และตรวจสอบได้ก่อน แล้วจึงพัฒนาให้ Strategy มีประสิทธิภาพมากขึ้น**
