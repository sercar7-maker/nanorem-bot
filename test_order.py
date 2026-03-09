from web.order_handler import OrderHandler
from core.partner_manager import PartnerManager
from core.commission import CommissionCalculator
from web.api_client import NanorvsAPIClient

# создаём зависимости
api_client = NanorvsAPIClient()
partner_manager = PartnerManager()
calculator = CommissionCalculator()

handler = OrderHandler(api_client, calculator)

# тестовый заказ
test_order = {
    "id": 1001,
    "partner_id": 2,
    "total_amount": 1000
}

handler.process_order(test_order)