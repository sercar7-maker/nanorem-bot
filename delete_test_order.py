from sqlalchemy import text

from database.db import SessionLocal

session = SessionLocal()

try:
    result = session.execute(
        text("DELETE FROM purchases WHERE ext_ref = :ext_ref"),
        {"ext_ref": "TEST123"}
    )
    session.commit()

    print(f"Удалено строк: {result.rowcount}")

finally:
    session.close()