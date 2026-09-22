# Workspace Rules & Development Protocols for Personal Algo-Trading Bot

> **คำสั่งบังคับสำหรับ AI Agent ทุกตัวที่ทำงานในโปรเจกต์นี้:**

1. **อัปเดต [DEVELOPMENT_LOG.md](file:///d:/AlgoTrading/DEVELOPMENT_LOG.md) ทุกครั้ง:**
   - ทุกครั้งที่มีการแก้ไขโค้ด, พัฒนาระบบใหม่, แก้ไขบัก, หรือทำการทดสอบ **ต้องมาอัปเดตบันทึกใน [DEVELOPMENT_LOG.md](file:///d:/AlgoTrading/DEVELOPMENT_LOG.md) เสมอ**
   - บันทึกให้ละเอียด: สิ่งที่ทำ, ไฟล์ที่สร้าง/แก้, ฟังก์ชันที่เพิ่ม, ปัญหาที่พบ, และงานที่ต้องทำถัดไป
   - อัปเดตสถานะใน Checklist ของ Phase นั้นๆ

2. **เมื่อสับสน, ลืมบริบท, หรือไม่แน่ใจ ให้กลับมาอ่านก่อนเสมอ:**
   - ให้อ่าน [UNIFIED_PLAN.md](file:///d:/AlgoTrading/UNIFIED_PLAN.md) เพื่อทำความเข้าใจสถาปัตยกรรม, Flow การทำงาน, กฎความปลอดภัย 12 ข้อ, และขอบเขตงาน
   - ให้อ่าน [DEVELOPMENT_LOG.md](file:///d:/AlgoTrading/DEVELOPMENT_LOG.md) เพื่อดูสถานะงานล่าสุด
   - **ห้ามเดาหรือสมมติการทำงานขึ้นมาเอง** ให้ยึดตามข้อกำหนดในสองไฟล์นี้เป็นหลัก

3. **กฎเหล็กทางสถาปัตยกรรม (Architecture Invariants):**
   - Concurrency ใช้ Python `asyncio` เป็นหลัก
   - บัญชี Alpaca Scope = **Trade Only** (ห้ามมีสิทธิ์ Withdraw เด็ดขาด)
   - ห้าม Commit ไฟล์ `.env`
   - ทุกคำสั่งซื้อต้องผูก **Bracket Order (Take Profit + Stop Loss)** ทันที
   - ต้องเคารพ **PDT Rule** (ทุน < $25,000 ห้าม Day Trade เกิน 3 ครั้งใน 5 วันทำการ)
   - ต้องทำ **Indicator Warmup (>= 100 bars)** ก่อนสร้าง Signal
   - AI (OpenRouter) ทำหน้าที่เป็น **Gatekeeper / Filter** เท่านั้น ห้ามตัดสินใจสั่งซื้อขายเอง
   - จัดเก็บข้อมูลวันเวลาทั้งหมดใน Database เป็น **UTC**
