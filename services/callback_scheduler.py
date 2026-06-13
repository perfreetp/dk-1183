from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
import asyncio
import logging

from config.database import SessionLocal
from services.callback_service import CallbackService

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def process_pending_callbacks():
    db = SessionLocal()
    try:
        pending_callbacks = CallbackService.get_pending_callbacks(db, limit=50)
        
        for callback in pending_callbacks:
            success = await CallbackService.send_callback(callback.id, db)
            if success:
                logger.info(f"Callback {callback.id} sent successfully")
            else:
                logger.warning(f"Callback {callback.id} failed")
    except Exception as e:
        logger.error(f"Error processing callbacks: {e}")
    finally:
        db.close()

def start_scheduler():
    scheduler.add_job(
        process_pending_callbacks,
        trigger=IntervalTrigger(seconds=30),
        id="process_callbacks",
        name="Process pending callbacks",
        replace_existing=True
    )
    scheduler.start()
    logger.info("Callback scheduler started")

def stop_scheduler():
    scheduler.shutdown()
    logger.info("Callback scheduler stopped")
