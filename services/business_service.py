from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import Session
from config.database import Base

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(50), unique=True, nullable=False, index=True)
    customer_id = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    total_amount = Column(Integer, default=0)
    items = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Customer(Base):
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100))
    email = Column(String(100))
    phone = Column(String(20))
    level = Column(String(20), default="normal")
    total_orders = Column(Integer, default=0)
    total_amount = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AfterSale(Base):
    __tablename__ = "aftersales"
    
    id = Column(Integer, primary_key=True, index=True)
    aftersale_id = Column(String(50), unique=True, nullable=False, index=True)
    order_id = Column(String(50), nullable=False)
    type = Column(String(20), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100))
    category = Column(String(50))
    price = Column(Integer, default=0)
    stock = Column(Integer, default=0)
    status = Column(String(20), default="available")
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class BusinessDataService:
    VALID_AFTERSALE_TYPES = ["refund", "exchange", "repair"]
    VALID_ORDER_STATUSES = ["pending", "processing", "shipped", "delivered", "completed", "cancelled"]
    
    @staticmethod
    def validate_aftersale_params(order_id: str, type: str, reason: str) -> Dict[str, Any]:
        errors = []
        
        if not order_id or len(order_id.strip()) == 0:
            errors.append({"field": "order_id", "message": "order_id 不能为空"})
        elif len(order_id) < 6 or len(order_id) > 50:
            errors.append({"field": "order_id", "message": "order_id 长度必须在6-50字符之间"})
        
        if not type or len(type.strip()) == 0:
            errors.append({"field": "type", "message": "type 不能为空"})
        elif type not in BusinessDataService.VALID_AFTERSALE_TYPES:
            errors.append({"field": "type", "message": f"type 必须是以下之一: {', '.join(BusinessDataService.VALID_AFTERSALE_TYPES)}"})
        
        if not reason or len(reason.strip()) == 0:
            errors.append({"field": "reason", "message": "reason 不能为空"})
        elif len(reason) > 500:
            errors.append({"field": "reason", "message": "reason 长度不能超过500字符"})
        
        return {"valid": len(errors) == 0, "errors": errors}
    
    @staticmethod
    def validate_order_status(new_status: str) -> Dict[str, Any]:
        errors = []
        
        if not new_status or len(new_status.strip()) == 0:
            errors.append({"field": "new_status", "message": "new_status 不能为空"})
        elif new_status not in BusinessDataService.VALID_ORDER_STATUSES:
            errors.append({"field": "new_status", "message": f"new_status 必须是以下之一: {', '.join(BusinessDataService.VALID_ORDER_STATUSES)}"})
        
        return {"valid": len(errors) == 0, "errors": errors}
    
    @staticmethod
    def get_order(db: Session, order_id: str) -> Optional[Order]:
        return db.query(Order).filter(Order.order_id == order_id).first()
    
    @staticmethod
    def create_order(db: Session, order_id: str, customer_id: str, 
                     total_amount: int = 0, items: list = None) -> Order:
        order = Order(
            order_id=order_id,
            customer_id=customer_id,
            status="pending",
            total_amount=total_amount,
            items=items or []
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order
    
    @staticmethod
    def update_order_status(db: Session, order_id: str, new_status: str) -> Optional[Order]:
        order = db.query(Order).filter(Order.order_id == order_id).first()
        if not order:
            return None
        
        previous_status = order.status
        order.status = new_status
        order.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(order)
        
        return order
    
    @staticmethod
    def get_customer(db: Session, customer_id: str) -> Optional[Customer]:
        return db.query(Customer).filter(Customer.customer_id == customer_id).first()
    
    @staticmethod
    def create_customer(db: Session, customer_id: str, name: str = None,
                        email: str = None, phone: str = None) -> Customer:
        customer = Customer(
            customer_id=customer_id,
            name=name,
            email=email,
            phone=phone
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return customer
    
    @staticmethod
    def get_aftersale(db: Session, aftersale_id: str) -> Optional[AfterSale]:
        return db.query(AfterSale).filter(AfterSale.aftersale_id == aftersale_id).first()
    
    @staticmethod
    def create_aftersale(db: Session, order_id: str, type: str, reason: str) -> AfterSale:
        import time
        aftersale_id = f"AS{int(time.time() * 1000)}"
        
        aftersale = AfterSale(
            aftersale_id=aftersale_id,
            order_id=order_id,
            type=type,
            reason=reason,
            status="pending"
        )
        db.add(aftersale)
        db.commit()
        db.refresh(aftersale)
        return aftersale
    
    @staticmethod
    def get_product(db: Session, product_id: str) -> Optional[Product]:
        return db.query(Product).filter(Product.product_id == product_id).first()
    
    @staticmethod
    def create_product(db: Session, product_id: str, name: str = None,
                       category: str = None, price: int = 0) -> Product:
        product = Product(
            product_id=product_id,
            name=name,
            category=category,
            price=price
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product
    
    @staticmethod
    def init_test_data(db: Session):
        if db.query(Order).count() == 0:
            test_order = Order(
                order_id="ORD123456",
                customer_id="CUST001",
                status="pending",
                total_amount=29999,
                items=[
                    {"product_id": "P001", "name": "Product A", "quantity": 2, "price": 9999},
                    {"product_id": "P002", "name": "Product B", "quantity": 1, "price": 10001}
                ]
            )
            db.add(test_order)
        
        if db.query(Customer).count() == 0:
            test_customer = Customer(
                customer_id="CUST001",
                name="张三",
                email="zhangsan@example.com",
                phone="138****8888",
                level="VIP",
                total_orders=50,
                total_amount=1500000
            )
            db.add(test_customer)
        
        if db.query(Product).count() == 0:
            test_product = Product(
                product_id="P001",
                name="Product A",
                category="Electronics",
                price=9999,
                stock=100,
                status="available"
            )
            db.add(test_product)
        
        db.commit()