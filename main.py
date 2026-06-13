from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
import logging

from config.database import engine, SessionLocal, Base
from models.database import ApiEndpoint
from services.error_service import ErrorService
from routers import partner_router, business_router, admin_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_database():
    try:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            ErrorService.initialize_error_codes(db)
            
            existing_apis = db.query(ApiEndpoint).count()
            if existing_apis == 0:
                apis = [
                    ApiEndpoint(
                        api_code="ORDER_QUERY",
                        api_name="订单查询",
                        category="order",
                        method="GET",
                        path="/api/v1/business/order/query",
                        description="根据订单号查询订单详情",
                        parameters={"order_id": {"type": "string", "required": True}},
                        request_example='{"order_id": "ORD123456"}',
                        response_example='{"order_id": "ORD123456", "status": "completed"}',
                        rate_limit=100,
                        version="1.0"
                    ),
                    ApiEndpoint(
                        api_code="CUSTOMER_QUERY",
                        api_name="客户查询",
                        category="customer",
                        method="GET",
                        path="/api/v1/business/customer/query",
                        description="根据客户号查询客户信息",
                        parameters={"customer_id": {"type": "string", "required": True}},
                        request_example='{"customer_id": "CUST123456"}',
                        response_example='{"customer_id": "CUST123456", "name": "张三"}',
                        rate_limit=100,
                        version="1.0"
                    ),
                    ApiEndpoint(
                        api_code="PRODUCT_QUERY",
                        api_name="商品查询",
                        category="product",
                        method="GET",
                        path="/api/v1/business/product/query",
                        description="根据商品号查询商品信息",
                        parameters={"product_id": {"type": "string", "required": True}},
                        request_example='{"product_id": "P001"}',
                        response_example='{"product_id": "P001", "name": "Product A"}',
                        rate_limit=200,
                        version="1.0"
                    ),
                    ApiEndpoint(
                        api_code="AFTERSALE_CREATE",
                        api_name="售后创建",
                        category="after_sale",
                        method="POST",
                        path="/api/v1/business/aftersale/create",
                        description="提交售后申请",
                        parameters={
                            "order_id": {"type": "string", "required": True},
                            "type": {"type": "string", "required": True, "enum": ["refund", "exchange", "repair"]},
                            "reason": {"type": "string", "required": True}
                        },
                        request_example='{"order_id": "ORD123456", "type": "refund", "reason": "商品损坏"}',
                        response_example='{"aftersale_id": "AS123456", "status": "pending"}',
                        rate_limit=50,
                        version="1.0"
                    ),
                    ApiEndpoint(
                        api_code="AFTERSALE_QUERY",
                        api_name="售后查询",
                        category="after_sale",
                        method="GET",
                        path="/api/v1/business/aftersale/query",
                        description="根据售后单号查询售后信息",
                        parameters={"aftersale_id": {"type": "string", "required": True}},
                        request_example='{"aftersale_id": "AS123456"}',
                        response_example='{"aftersale_id": "AS123456", "status": "processing"}',
                        rate_limit=100,
                        version="1.0"
                    ),
                    ApiEndpoint(
                        api_code="ORDER_STATUS_UPDATE",
                        api_name="订单状态更新",
                        category="order",
                        method="POST",
                        path="/api/v1/business/order/status/update",
                        description="更新订单状态",
                        parameters={
                            "order_id": {"type": "string", "required": True},
                            "new_status": {"type": "string", "required": True}
                        },
                        request_example='{"order_id": "ORD123456", "new_status": "shipped"}',
                        response_example='{"order_id": "ORD123456", "new_status": "shipped"}',
                        rate_limit=50,
                        version="1.0"
                    )
                ]
                for api in apis:
                    db.add(api)
                db.commit()
                logger.info("Initialized 6 API endpoints")
            
            from services.business_service import BusinessDataService
            BusinessDataService.init_test_data(db)
            logger.info("Initialized test data")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Database initialization failed: {e}. Service will start anyway.")
        logger.info("Service starting without database initialization")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up API Platform...")
    init_database()
    from services.callback_scheduler import start_scheduler
    start_scheduler()
    yield
    from services.callback_scheduler import stop_scheduler
    stop_scheduler()
    logger.info("Shutting down API Platform...")

app = FastAPI(
    title="公共 API 开放平台",
    description="面向合作伙伴开放订单、客户、商品和售后等基础能力",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(partner_router.router)
app.include_router(business_router.router)
app.include_router(admin_router.router)

@app.get("/")
async def root():
    return {
        "service": "公共 API 开放平台",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "Internal server error",
            "error_code": "SYSTEM_001",
            "request_id": None
        }
    )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
