from sqlalchemy.orm import Session

from database.db import SessionLocal
from database.models_stats import PartnerStats


class MonthlyResetService:

    @staticmethod
    def reset_monthly_turnover():

        session: Session = SessionLocal()

        try:

            stats_list = session.query(PartnerStats).all()

            for stats in stats_list:
                stats.monthly_personal_turnover = 0
                stats.monthly_network_turnover = 0

            session.commit()

        finally:
            session.close()