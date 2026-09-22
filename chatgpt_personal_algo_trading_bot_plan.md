# Personal Algo-Trading Bot

## 1. Project Objective

สร้าง **ระบบเทรดหุ้นสหรัฐฯ อัตโนมัติส่วนตัว (Personal Algo-Trading Bot)** สำหรับพอร์ตเริ่มต้นประมาณ **$700**

ระบบต้องสามารถ:

- รับข้อมูลตลาดหุ้นสหรัฐฯ
- วิเคราะห์ Technical
- สร้าง Trading Signal
- วิเคราะห์ข่าวด้วย AI / Sentiment
- ควบคุมความเสี่ยง
- คำนวณ Position Size
- ส่งคำสั่งซื้อขายอัตโนมัติ
- รองรับ Scaling
- รองรับ Take Profit / Stop Loss
- ติดตาม Orders และ Positions
- ทำงานบน VPS อย่างต่อเนื่อง
- ตรวจจับและรับมือกับความผิดปกติ
- บันทึกข้อมูลลง Database
- มี Dashboard และ Monitoring
- Backtest และ Paper Trading ก่อน Live Trading

### หลักการสำคัญ

**Technical เป็นตัวสร้างสัญญาณ → AI เป็นตัวช่วยวิเคราะห์ข่าว → Risk Engine ควบคุมความเสี่ยง → Order Engine ส่งคำสั่ง → Portfolio/State Management ติดตามสถานะ → Monitoring ดูแลระบบ**

เป้าหมายระยะแรกไม่ใช่การทำกำไรสูงสุด แต่คือการสร้างระบบที่ทำงานถูกต้อง ควบคุมความเสี่ยงได้ และสามารถตรวจสอบย้อนหลังได้

---

# 2. System Components

ระบบแบ่งออกเป็นส่วนหลักดังนี้

## 2.1 Market Data

รับข้อมูลตลาดหุ้นสหรัฐฯ ทั้ง Real-time และ Historical Data เพื่อใช้กับ Strategy และระบบอื่น

## 2.2 Technical Analysis

วิเคราะห์ข้อมูลราคาด้วย Technical Indicators และสร้างข้อมูลประกอบการตัดสินใจ

## 2.3 Strategy Engine

กำหนดกฎของกลยุทธ์และสร้าง Trading Signal เช่น Buy / Sell / Hold

Strategy ต้องเป็นกฎที่ชัดเจนและสามารถ Backtest ได้

## 2.4 AI / Sentiment Analysis

วิเคราะห์ข่าวสารและเหตุการณ์ที่เกี่ยวข้องกับหุ้น

AI ทำหน้าที่เป็น **Filter / Supporting Signal** ไม่ใช่ผู้ตัดสินใจซื้อขายเพียงลำพัง

## 2.5 Risk Management

ควบคุมความเสี่ยงของระบบและแต่ละ Trade เช่น:

- Maximum Risk
- Maximum Position
- Maximum Exposure
- Maximum Daily Loss
- Trading Limits
- Kill Switch

ทุก Trading Signal ต้องผ่าน Risk Management ก่อนส่ง Order

## 2.6 Position Sizing

คำนวณขนาด Position ให้สัมพันธ์กับระดับความเสี่ยงที่กำหนด

## 2.7 Order Execution

จัดการการส่งคำสั่งไปยัง Alpaca รวมถึง:

- Submit Order
- Cancel Order
- Order Status
- Fill
- Partial Fill
- Bracket Order
- Take Profit
- Stop Loss
- Scaling

## 2.8 Portfolio & State Management

ติดตามสถานะจริงของ:

- Account
- Cash
- Buying Power
- Orders
- Positions
- Portfolio
- Bot State

ระบบต้องสามารถตรวจสอบและกู้คืนสถานะหลัง Restart หรือ Connection Failure ได้

## 2.9 Database

ใช้ PostgreSQL สำหรับเก็บข้อมูลสำคัญของระบบ เช่น:

- Signals
- Orders
- Fills
- Positions
- Portfolio
- News
- AI Analysis
- Risk Events
- System Events
- Bot State
- Strategy Configuration

## 2.10 Monitoring & Dashboard

ใช้สำหรับตรวจสอบ:

- Bot Status
- Account
- Portfolio
- Positions
- Orders
- Signals
- Risk
- AI Sentiment
- System Health
- Error / Warning

รวมถึงระบบแจ้งเตือนเมื่อเกิดเหตุการณ์สำคัญ

---

# 3. Technology Stack

## Trading Platform

- Alpaca Trading API
- Alpaca Paper Trading
- Alpaca Live Trading ในภายหลัง

## Backend

- Python 3.x

## Database

- PostgreSQL

## AI

- OpenRouter / LLM API
- สามารถพิจารณา Ollama / Local LLM ในอนาคต

## Server

- Ubuntu 24.04
- VPS
- Docker หรือ systemd สำหรับจัดการ Service
- Nginx ตามความเหมาะสม

## Frontend / Dashboard

เลือกใช้:

- Angular
- หรือ Next.js

โดย Dashboard ไม่ใช่ส่วนที่ต้องทำก่อน Trading Core

## Development

- Git
- VS Code / Google Antigravity IDE
- Environment Variables
- Logging
- Testing

---

# 4. Development Phases

## Phase 1 — Preparation

เตรียมสิ่งจำเป็นทั้งหมด:

- Alpaca Account
- Paper Trading
- API Key / Secret
- Development Environment
- Git Repository
- Python Environment
- PostgreSQL
- Project Configuration
- Environment Variables

ช่วงนี้ยังไม่ใช้เงินจริง

---

## Phase 2 — Alpaca API Integration

พัฒนา Integration Layer สำหรับ Alpaca

ระบบต้องสามารถ:

- อ่าน Account
- อ่าน Buying Power
- อ่าน Market Data
- อ่าน Orders
- อ่าน Positions
- ส่ง Order
- ยกเลิก Order
- ตรวจสอบ Order Status
- เชื่อมต่อ Real-time Data

เป้าหมายคือทำให้ Trading Core สามารถสื่อสารกับ Alpaca ได้อย่างเป็นระบบ

---

## Phase 3 — Database & State Management

สร้าง Database และระบบจัดการ State

เป้าหมายคือให้ระบบรู้สถานะของตัวเองและสถานะการเทรดอยู่ตลอดเวลา

ต้องรองรับ:

- Bot Start / Stop
- Order State
- Position State
- Portfolio State
- Error State
- Recovery
- Reconciliation

เมื่อ Bot Restart ต้องสามารถตรวจสอบสถานะจริงจาก Alpaca และนำกลับมา Sync กับ Database ได้

---

## Phase 4 — Market Data

พัฒนาระบบรับและจัดการ Market Data

รองรับ:

- Real-time Data
- Historical Data
- Data Validation
- Connection Handling
- Data Staleness Detection

ข้อมูล Market Data ต้องสามารถนำไปใช้กับทั้ง Strategy และ Backtesting

---

## Phase 5 — Technical Strategy

พัฒนา Technical Analysis และ Strategy

กำหนด:

- Indicators
- Entry Conditions
- Exit Conditions
- Signal Rules
- Strategy Configuration

Strategy ต้องเป็นกฎที่ชัดเจน สามารถทำซ้ำและ Backtest ได้

ช่วงแรกควรเริ่มจาก Strategy ที่เรียบง่ายก่อน

---

## Phase 6 — Backtesting

นำ Strategy ไปทดสอบกับ Historical Data

ระบบ Backtest ต้องสามารถจำลอง:

- Entry
- Exit
- Position
- Take Profit
- Stop Loss
- Scaling
- Trading Cost ที่เกี่ยวข้อง
- Performance

และวัดผล เช่น:

- Total Return
- Win Rate
- Average Win
- Average Loss
- Profit Factor
- Maximum Drawdown
- Sharpe Ratio
- Expectancy
- Number of Trades
- Consecutive Losses

ต้องทดสอบกับหลายสภาวะตลาด ไม่ใช่เฉพาะช่วงตลาดขาขึ้น

---

## Phase 7 — Risk Management

สร้าง Risk Engine เป็นส่วนกลางของระบบ

ทุก Signal ต้องผ่าน Risk Engine ก่อนส่งคำสั่ง

Risk Engine ต้องควบคุม:

- Risk per Trade
- Position Size
- Maximum Position
- Maximum Exposure
- Maximum Daily Loss
- จำนวน Position
- จำนวน Trade
- Market Session
- Duplicate Order
- Stale Market Data
- Account / Position Anomaly

Risk Engine สามารถปฏิเสธ Trade ได้แม้ Strategy จะสร้าง BUY Signal

---

## Phase 8 — Position Sizing

พัฒนาระบบคำนวณ Position Size ตาม Risk

Position Size ต้องสัมพันธ์กับ:

- Account Equity
- Maximum Risk
- Entry Price
- Stop Loss
- Current Exposure
- Buying Power
- Maximum Position

ไม่ควรกำหนดขนาด Position แบบตายตัวโดยไม่คำนึงถึง Risk

---

## Phase 9 — Order Execution

พัฒนา Execution Engine

รองรับ:

- Market / Limit Order ตาม Strategy
- Bracket Order
- Take Profit
- Stop Loss
- Scaling
- Partial Fill
- Order Rejection
- Order Timeout
- Cancel / Replace
- Retry
- Order Monitoring

หลังจากส่ง Order แล้วระบบต้องติดตามผลลัพธ์จริง ไม่ถือว่าการ Submit สำเร็จหมายถึง Position สำเร็จทันที

---

## Phase 10 — AI Sentiment

เพิ่ม AI สำหรับวิเคราะห์ข่าวและเหตุการณ์ของหุ้น

Flow:

**News → Filtering → AI Analysis → Structured Sentiment → Strategy / Risk Filter**

AI Output ควรเป็นข้อมูลที่ระบบนำไปประมวลผลต่อได้ เช่น:

- Sentiment
- Confidence
- Direction
- Impact
- Risk Event
- Time Horizon

AI ไม่ควรเป็นผู้ตัดสินใจซื้อขายเพียงลำพัง

---

## Phase 11 — Strategy + AI Integration

รวม Technical Strategy กับ AI Sentiment

Flow:

**Market Data → Technical Signal → AI Sentiment → Risk Engine → Order**

AI สามารถ:

- สนับสนุน Signal
- กรอง Signal
- เพิ่ม Warning
- ปฏิเสธ Trade ในกรณีที่มี Risk Event

ต้องสามารถแยกวิเคราะห์ได้ว่า AI ช่วยหรือทำให้ Strategy แย่ลง

---

## Phase 12 — Paper Trading

นำระบบทั้งหมดมาทดสอบกับ Alpaca Paper Trading

ทดสอบ End-to-End:

- Market Data
- Technical
- Strategy
- AI
- Risk
- Position Sizing
- Order
- Bracket
- Scaling
- Fill
- Position
- Database
- Recovery
- Monitoring

ต้องตรวจสอบทั้งกรณีปกติและกรณีผิดพลาด

ไม่ควรตัดสิน Strategy จาก Paper Trading เพียงระยะเวลาสั้น ๆ

---

## Phase 13 — Fail-safe & Recovery

สร้างระบบป้องกันความผิดพลาด

ตัวอย่างประเภทเหตุการณ์:

- API Failure
- Network Failure
- WebSocket Disconnect
- Market Data Stale
- Duplicate Order
- Position Mismatch
- Database Error
- Unexpected Order
- Daily Loss Limit
- Bot Crash
- Server Restart

เมื่อเกิดเหตุการณ์ร้ายแรง ระบบต้องสามารถ:

- หยุดเปิด Trade ใหม่
- เข้าสู่ Safe Mode
- Cancel Pending Orders ตามเงื่อนไข
- Reconcile Position
- แจ้งเตือน
- ใช้ Kill Switch

---

## Phase 14 — Monitoring & Dashboard

สร้าง Dashboard สำหรับดูระบบโดยไม่ต้องเข้า Server โดยตรง

แสดงข้อมูลหลัก:

- Bot Status
- Account
- Equity
- Cash
- Buying Power
- P/L
- Positions
- Orders
- Signals
- Technical Data
- AI Sentiment
- Risk Status
- System Health
- Logs / Events

ควรมีระบบแจ้งเตือนเมื่อเกิดเหตุการณ์สำคัญ

---

## Phase 15 — VPS Deployment

นำระบบขึ้น VPS

เตรียม:

- Ubuntu
- Python
- PostgreSQL
- Application
- Environment Variables
- Process Management
- Logging
- Monitoring
- Firewall / Security
- Backup

Bot ต้องสามารถทำงานต่อเนื่องและ Restart ได้อย่างปลอดภัย

---

## Phase 16 — Live Trading

เมื่อระบบผ่าน Backtesting และ Paper Trading แล้วจึงพิจารณา Live Trading

เริ่มต้นด้วยทุนประมาณ **$700**

หลักการ:

- เริ่มจาก Risk ต่ำ
- ไม่เพิ่มความเสี่ยงทันที
- ตรวจสอบ Live Execution
- ตรวจสอบ Slippage / Fill
- ตรวจสอบความแตกต่างระหว่าง Backtest / Paper / Live
- มี Kill Switch พร้อมใช้งาน

---

## Phase 17 — Performance Analysis

เก็บข้อมูล Live Trading และวิเคราะห์ผลอย่างต่อเนื่อง

วิเคราะห์:

- Performance
- Win / Loss
- Profit Factor
- Drawdown
- Expectancy
- Risk
- Execution
- Slippage
- Strategy Behavior
- AI Effectiveness
- Market Regime

เป้าหมายคือใช้ข้อมูลจริงเพื่อประเมิน Strategy ไม่ใช่ดูเฉพาะกำไร/ขาดทุนรวม

---

## Phase 18 — Optimization

นำผลจาก Backtest, Paper Trading และ Live Trading มาปรับปรุงระบบ

ปรับได้ทั้ง:

- Strategy
- Risk Management
- Position Sizing
- AI Filter
- Execution
- Monitoring

การปรับ Strategy ต้องมีการทดสอบซ้ำ และหลีกเลี่ยงการปรับตามผลลัพธ์ระยะสั้นจนเกิด Overfitting

---

# 5. Runtime Flow

เมื่อระบบทำงานจริง ลำดับหลักคือ:

**Market Data**

↓

**Technical Analysis**

↓

**Trading Signal**

↓

**AI / Sentiment Analysis**

↓

**Risk Management**

↓

**Position Sizing**

↓

**Trade Approval / Rejection**

↓

**Order Execution**

↓

**Order / Fill Monitoring**

↓

**Position Management**

↓

**Take Profit / Stop Loss / Scaling**

↓

**Database**

↓

**Monitoring / Alert**

↓

**รอ Signal ถัดไป**

---

# 6. Reliability Requirements

ระบบต้องออกแบบโดยคำนึงถึงกรณีผิดพลาดตั้งแต่ต้น

ต้องรองรับ:

- Bot Restart
- Server Restart
- API Timeout
- API Error
- Network Failure
- WebSocket Disconnect
- Database Failure
- Duplicate Signal
- Duplicate Order
- Partial Fill
- Order Rejection
- Position Mismatch
- Stale Market Data
- Unexpected Account State

หลักการสำคัญ:

> ระบบต้องไม่ส่ง Order ใหม่เพียงเพราะไม่สามารถอ่านสถานะเดิมได้

ก่อนกลับมา Trade ต้องตรวจสอบและ Reconcile สถานะจริงก่อน

---

# 7. สิ่งที่ยังไม่ทำในช่วงแรก

เพื่อควบคุมความซับซ้อนของ Project ให้เริ่มจากระบบพื้นฐานก่อน

ยังไม่เน้น:

- Deep Learning
- Reinforcement Learning
- Complex Machine Learning
- LLM ที่ตัดสินใจซื้อขายโดยตรง
- หุ้นจำนวนมาก
- Options
- Leverage
- Futures
- High-Frequency Trading
- Distributed Infrastructure ที่ไม่จำเป็น

---

# 8. Version 1 Scope

Version 1 ต้องสามารถทำงานครบวงจร:

**Market Data**

→ **Technical Strategy**

→ **AI Sentiment Filter**

→ **Risk Management**

→ **Position Sizing**

→ **Order Execution**

→ **Position Management**

→ **Database**

→ **Monitoring**

และต้องสามารถผ่านกระบวนการ:

**Backtest → Paper Trading → VPS Deployment → Live Trading**

โดยไม่จำเป็นต้องรื้อ Architecture ใหม่

---

# 9. Development Order

ลำดับการพัฒนาหลัก:

1. Preparation
2. Alpaca API Integration
3. Database & State Management
4. Market Data
5. Technical Strategy
6. Backtesting
7. Risk Management
8. Position Sizing
9. Order Execution
10. AI Sentiment
11. Strategy + AI Integration
12. Paper Trading
13. Fail-safe & Recovery
14. Monitoring & Dashboard
15. VPS Deployment
16. Live Trading
17. Performance Analysis
18. Optimization

---

# 10. Core Architecture

```text
Personal Algo-Trading Bot
│
├── Market Data
│
├── Technical Engine
│
├── Strategy Engine
│
├── AI / Sentiment Engine
│
├── Risk Engine
│
├── Position Sizing
│
├── Order Execution
│
├── Portfolio & State Management
│
├── PostgreSQL
│
├── Monitoring & Alert
│
└── Dashboard
        │
        ▼
     Alpaca API
        │
        ▼
   US Stock Market
```

---

# 11. Core Principles

1. Technical Strategy เป็นแกนหลักของการสร้าง Signal
2. AI เป็นตัวช่วยวิเคราะห์ข่าวและเป็น Filter
3. ทุก Trade ต้องผ่าน Risk Management
4. Position Size ต้องสัมพันธ์กับ Risk
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
15. การปรับปรุง Strategy ต้องอาศัยข้อมูลและการทดสอบ ไม่ใช่ผลลัพธ์ระยะสั้นเพียงอย่างเดียว

---

# 12. Final Project Goal

เป้าหมายสุดท้ายคือสร้างระบบที่สามารถ:

**รับข้อมูลตลาด → วิเคราะห์ → สร้าง Signal → ตรวจสอบข่าวด้วย AI → ประเมินความเสี่ยง → คำนวณ Position → ส่งคำสั่ง → ติดตาม Position → ปิด Position ตาม Strategy → บันทึกข้อมูล → Monitor → Recover เมื่อเกิดปัญหา → วิเคราะห์ Performance → ปรับปรุง Strategy**

โดยระบบสามารถทำงานอัตโนมัติบน VPS และสามารถเปลี่ยนผ่านจาก **Backtest → Paper Trading → Live Trading** ได้อย่างเป็นระบบ

> **หลักคิดของโครงการ: สร้างระบบ Trading ที่ควบคุมได้และตรวจสอบได้ก่อน แล้วจึงพัฒนาให้ Strategy มีประสิทธิภาพมากขึ้น**
